#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""检查站点的 HTML 页面：结构、导航一致性、内外链、零外部依赖、窄屏溢出风险。

与 check_readme.py 互补：那个管 README.md，这个管各个 HTML 页面。
只用标准库。有问题时退出码为 1。

用法：python .github/scripts/check_site.py [页面...]
      不带参数时自动检查仓库根目录下的所有 *.html
"""
import os
import re
import sys
import json
import base64
import unicodedata
import urllib.request
import urllib.error
import urllib.parse
from html.parser import HTMLParser

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/124.0 Safari/537.36")

PLACEHOLDER = [r"<user>", r"<repo>", r"your-username", r"\bTODO\b", r"\bFIXME\b", r"\bXXX\b"]

# 这些站点对程序化请求一律返回 404（反爬），CI 无法据此判断链接是否失效。
# 记为「无法自动验证」的警告，不计失败；需人工在 App 或浏览器里确认。
NO_VERIFY_HOSTS = ("douyin.com", "v.douyin.com", "www.douyin.com")

# 窄屏预算：320px 视口 - wrap 左右 22*2 - 卡片内边距约 20*2 - 序号区 24
NARROW_BUDGET_PX = 226
# 单个字符宽度估算系数（相对字号）
WIDE, ASCII, DIGIT = 1.0, 0.60, 0.56

VOID_TAGS = {"br", "hr", "img", "input", "meta", "link", "source", "area",
             "base", "col", "embed", "param", "track", "wbr"}

# 站长 2026-11-07 素材规则（原话「链接改为 blob 格式」，当时被误听成 blog，
# 同日纠正）：仓库只留 .enc 密文容器，页面 img 只写 data-enc 不写 src，
# 浏览器本地解密后由 URL.createObjectURL 生成 blob: 地址。
# 登记两张存量截图的「明文名 → 密文路径」，Parser 与 check_asset_policy 共用。
REGISTERED_MEDIA = {
    "soul-2019-comments-1.jpg": "assets/soul-2019-comments-1.jpg.enc",
    "soul-2019-comments-2.jpg": "assets/soul-2019-comments-2.jpg.enc",
}


def _utf8():
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass


class Parser(HTMLParser):
    """一次遍历收集：标签配对、文本、a 标签、src/href 属性。"""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.stack = []
        self.errors = []
        self.texts = []
        self.links = []          # (href, target, rel)
        self.external_assets = []  # src / stylesheet 指向 http
        self.in_inert = None      # style/script 内部文本忽略

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if tag in ("style", "script"):
            self.in_inert = tag
        if tag == "a":
            self.links.append((a.get("href", ""), a.get("target", ""), a.get("rel", "")))
        if tag == "img" and a.get("src", "").startswith("http"):
            # 零外部依赖不再留任何白名单：素材一律走 .enc 解密后的 blob: URL，
            # 页面源码里出现 http 开头的 img src 就是回潮，直接判红。
            self.external_assets.append("img src=" + a["src"])
        if tag == "script" and a.get("src", "").startswith("http"):
            self.external_assets.append("script src=" + a["src"])
        if tag == "link" and a.get("href", "").startswith("http") and \
                "stylesheet" in (a.get("rel") or ""):
            self.external_assets.append("link stylesheet=" + a["href"])
        if tag not in VOID_TAGS:
            self.stack.append((tag, self.getpos()[0]))

    def handle_startendtag(self, tag, attrs):
        # HTMLParser 遇到 <img />、<br /> 这类自闭合写法会回调本方法，
        # 基类默认实现是「handle_starttag + handle_endtag」各调一次。但 VOID_TAGS
        # 本来就刻意不入栈（第 71 行），补的那次闭标签回调会拿真正的栈顶（如 figure）
        # 去对 img，误报「标签不配对」。2026-11-06 加两张本地截图时踩到。
        # 显式覆写：空元素只走开标签；非空元素仍按「开+闭」配对，原检查强度不变。
        self.handle_starttag(tag, attrs)
        if tag not in VOID_TAGS:
            self.handle_endtag(tag)

    def handle_endtag(self, tag):
        if tag in ("style", "script"):
            self.in_inert = None
        if not self.stack or self.stack[-1][0] != tag:
            self.errors.append("</%s> 行%s 栈顶=%s" % (
                tag, self.getpos()[0], self.stack[-1][0] if self.stack else "空"))
            return
        self.stack.pop()

    def handle_data(self, data):
        if self.in_inert:
            return
        if data.strip():
            self.texts.append(data)


def char_w(ch, fs):
    if ch == " ":
        return fs * 0.28
    if unicodedata.east_asian_width(ch) in ("W", "F"):
        return fs * WIDE
    return fs * (DIGIT if ch.isdigit() else ASCII)


def longest_token_px(text, fs=16.0):
    """渲染文本中最长不可断词的估算像素宽（中文/全角可断行，故风险只来自拉丁串）。"""
    best = cur = 0.0
    for ch in text:
        if ch == " " or unicodedata.east_asian_width(ch) in ("W", "F"):
            best = max(best, cur)
            cur = 0.0
        else:
            cur += char_w(ch, fs)
    return max(best, cur)


def nav_and_footer(html):
    nav = re.search(r'<nav class="navwrap">(.*?)</nav>', html, re.S)
    foot = re.search(r"<footer.*?</footer>", html, re.S)
    def hrefs(seg):
        return re.findall(r'href="\./([a-z0-9._-]+\.html)"', seg) if seg else []
    return hrefs(nav.group(1) if nav else None), hrefs(foot.group(0) if foot else None), bool(nav), bool(foot)


def probe(url, timeout=30, retries=2):
    THROTTLE = (401, 403, 429)
    last = ""
    for attempt in range(retries):
        for method in ("HEAD", "GET"):
            try:
                req = urllib.request.Request(url, headers={"User-Agent": UA}, method=method)
                with urllib.request.urlopen(req, timeout=timeout) as resp:
                    return "ok", "HTTP %s" % resp.status
            except urllib.error.HTTPError as e:
                last = "HTTP %s" % e.code
                if method == "HEAD" and e.code in (400, 401, 403, 405, 406, 429, 501):
                    continue
                if e.code in THROTTLE:
                    return "throttle", last + "（疑似限流，非失效）"
                return "dead", last
            except Exception as e:
                last = "%s: %s" % (type(e).__name__, str(e)[:50])
                if method == "HEAD":
                    continue
                break
        if attempt + 1 < retries:
            import time
            time.sleep(3)
    return "dead", last or "未知失败"


def check_page(path, repo_files, check_remote):
    raw = open(path, encoding="utf-8").read()
    name = os.path.basename(path)
    issues, notes = [], []

    p = Parser()
    p.feed(raw)
    issues += ["标签不配对: " + e for e in p.errors]
    issues += ["标签未闭合: <%s> 行%s" % (t, l) for t, l in p.stack]

    if not raw.lstrip().startswith("<!DOCTYPE html>"):
        issues.append("首行不是 <!DOCTYPE html>（会导致怪异模式）")
    if not re.search(r'<html[^>]+lang="', raw):
        issues.append("html 缺少 lang 属性")
    if not re.search(r"<title>[^<]{2,}</title>", raw):
        issues.append("缺少或过短的 <title>")
    if 'name="viewport"' not in raw:
        issues.append("缺少 viewport meta（移动端排版前提）")
    if name != "404.html":
        if "<noscript>" not in raw:
            issues.append("缺少 noscript 降级")
        if "@media (prefers-reduced-motion: reduce)" not in raw:
            issues.append("缺少 CSS 层 prefers-reduced-motion")

    # 占位符（剔除 style/script 后扫描）
    visible = re.sub(r"<(style|script)[^>]*>.*?</\1>", "", raw, flags=re.S)
    for pat in PLACEHOLDER:
        for m in re.finditer(pat, visible, re.I):
            issues.append("占位符 %r 行%s" % (m.group(0), visible[:m.start()].count("\n") + 1))

    # 零外部依赖
    if p.external_assets:
        issues.append("存在外部资源: " + "; ".join(p.external_assets))

    # target=_blank 必须带 noopener
    unsafe = [h for h, t, r in p.links if t == "_blank" and "noopener" not in (r or "")]
    if unsafe:
        issues.append("target=_blank 缺 noopener: " + ", ".join(u[:60] for u in unsafe[:3]))

    # 内链必须存在
    internal = sorted({h[2:] for h, t, r in p.links if h.startswith("./")})
    for ref in internal:
        if ref not in repo_files:
            issues.append("内链指向不存在的文件: ./%s" % ref)

    # 窄屏溢出风险
    text = " ".join(p.texts)
    worst = max((longest_token_px(w) for w in text.split()), default=0.0)
    if worst > NARROW_BUDGET_PX:
        tok = max(text.split(), key=lambda w: longest_token_px(w), default="")
        issues.append("窄屏溢出风险: 最长不可断词约 %.0fpx > 预算 %dpx（%r）"
                      % (worst, NARROW_BUDGET_PX, tok[:40]))
    else:
        notes.append("最长不可断词 %.0fpx（预算 %dpx）" % (worst, NARROW_BUDGET_PX))

    # 外链可达
    remote = sorted({h for h, t, r in p.links if h.startswith("http")})
    ok = warn = dead = 0
    unverifiable = []
    for url in (remote if check_remote else []):
        host = urllib.parse.urlparse(url).netloc.lower()
        if any(host == d or host.endswith("." + d) for d in NO_VERIFY_HOSTS):
            unverifiable.append(url)
            continue
        state, info = probe(url)
        if state == "ok":
            ok += 1
        elif state == "throttle":
            warn += 1
            notes.append("限流 %s (%s)" % (url, info))
        else:
            dead += 1
            issues.append("外链失效 %s -> %s" % (url, info))
    if remote:
        notes.append("外链 %d 个: 通过%d 限流%d 失败%d" % (len(remote), ok, warn, dead))
    if unverifiable:
        notes.append("无法自动验证 %d 个（该站点对程序请求一律返回 404，需人工在 App 内确认）:" % len(unverifiable))
        for u in unverifiable:
            notes.append("    ? %s" % u[:78])

    return name, issues, notes, nav_and_footer(raw)


# ---------------------------------------------------------------------------
# 素材规则（站长 2026-11-07 写死；同日纠正：站长说的是 blob，不是 blog）
#   「除非我明确表示明文，否则都使用 blob，此规则记录在 GitHub 仓库 README，写死规则」
# 落地形态参照 shuangxiugou/why-shuangxiugou.html 的「照片彩蛋」：
#   仓库只留 .enc 密文 → 浏览器 PBKDF2+AES-GCM 本地解密 →
#   URL.createObjectURL 生成 blob: 地址写进 img.src。
# 规则不能只写进 README：这里同时锁 ① 规则原文 ② 仓库内零明文素材
# ③ 密文容器结构有效 ④ img 只写 data-enc 且不放静态图片地址
# ⑤ 解密脚本真用 createObjectURL（口令两端一致）⑥ 点击放大 ⑦ 事实纠正不回流。
# ---------------------------------------------------------------------------
# REGISTERED_MEDIA 定义在模块顶部（Parser 也要用），此处不重复定义。
MEDIA_EXT = (".jpg", ".jpeg", ".png", ".webp", ".gif",
             ".mp4", ".mov", ".webm", ".pdf")
ASSET_RULE_MARKERS = (
    "除非站长明确表示「明文」",
    "blob 格式",
    "不得把素材原始文件明文提交进 GitHub 仓库",
    "密文容器",
    "URL.createObjectURL",
)
# 页面里不允许再出现「blog 格式链接」这条被纠正掉的错误规则
STALE_RULE_MARKERS = ("blog 格式链接", "/blog/")

VAULT_REQUIRED = (
    "createObjectURL(",
    "return impl.createObjectURL(blob);",
    "subtle.decrypt",
    "getAttribute('data-enc')",
    "setAttribute('src', urls[j])",
    "grid.hidden = false;",
    "PBKDF2",
)


def _b64ok(value, want_len=None):
    try:
        raw = base64.b64decode(value, validate=True)
    except Exception:
        return False
    return bool(raw) and (want_len is None or len(raw) == want_len)


def check_asset_policy(root, pages):
    issues, notes = [], []

    # ① README 规则原文
    readme = os.path.join(root, "README.md")
    if not os.path.exists(readme):
        issues.append("README.md 不存在，素材规则无处可查")
        text = ""
    else:
        with open(readme, encoding="utf-8") as f:
            text = f.read()
        missing = [m for m in ASSET_RULE_MARKERS if m not in text]
        if missing:
            issues.append("README 缺少素材规则原文：" + " / ".join(missing))
        # 只查「扩展约定」里的现行规则；变更记录里如实保留误听 blog 的历史，不改写历史。
        rules_part = text.split("## 变更记录", 1)[0]
        stale = [m for m in STALE_RULE_MARKERS if m in rules_part]
        if stale:
            issues.append("README 现行规则里仍写着已被纠正的 blog 说法：" + " / ".join(stale))

    # ② 整个仓库（工作区）不得躺着任何明文素材；.enc 不在此列
    for dirpath, dirnames, filenames in os.walk(root):
        if ".git" in dirnames:
            dirnames.remove(".git")
        for fn in sorted(filenames):
            if fn.lower().endswith(MEDIA_EXT):
                issues.append("仓库内出现明文素材 %s —— 只准留 .enc 密文容器"
                              % os.path.relpath(os.path.join(dirpath, fn), root))

    # ③ 密文容器：两张都必须存在、结构有效、名字对得上；多余的 .enc 要登记
    adir = os.path.join(root, "assets")
    known_enc = {os.path.basename(p) for p in REGISTERED_MEDIA.values()}
    if os.path.isdir(adir):
        for fn in sorted(os.listdir(adir)):
            if fn.endswith(".enc") and fn not in known_enc:
                issues.append("assets/ 出现未登记的密文素材 %s —— 新素材须先登记" % fn)
    for name, rel in sorted(REGISTERED_MEDIA.items()):
        p = os.path.join(root, rel)
        if not os.path.exists(p):
            issues.append("密文容器缺失：%s" % rel)
            continue
        try:
            with open(p, encoding="utf-8") as f:
                c = json.load(f)
        except Exception as e:
            issues.append("密文容器 %s 不是合法 JSON：%s" % (rel, e))
            continue
        if c.get("v") != 1 or c.get("iter") != 210000 \
                or "AES-256-GCM" not in str(c.get("alg", "")):
            issues.append("密文容器 %s 版本/算法/迭代次数不对（须 v=1、21 万次、AES-256-GCM）" % rel)
        if c.get("name") != name or c.get("type") != "image/jpeg":
            issues.append("密文容器 %s 的 name/type 与登记不符" % rel)
        for field, want in (("salt", 16), ("iv", 12), ("tag", 16), ("data", None)):
            if not _b64ok(c.get(field, ""), want):
                issues.append("密文容器 %s 的 %s 不是有效 base64（或长度不对）" % (rel, field))

    # ④ 页面：img 只写 data-enc、不放静态图片地址；两张都登记
    seen = set()
    for rel in pages:
        path = rel if os.path.isabs(rel) else os.path.join(root, rel)
        if not os.path.exists(path):
            continue
        with open(path, encoding="utf-8") as f:
            raw = f.read()
        imgs = re.findall(r"<img\b[^>]*>", raw)
        for tag in imgs:
            if re.search(r"\bsrc\s*=", tag):
                issues.append("%s 的 img 写死了 src（%s）—— 素材必须由解密后的 blob: 地址注入"
                              % (os.path.basename(path), tag.strip()[:90]))
            m = re.search(r'data-enc="([^"]+)"', tag)
            if m:
                enc = m.group(1)
                base = os.path.basename(urllib.parse.urlparse(enc).path)
                plain_name = base[:-4] if base.endswith(".enc") else base
                if plain_name not in REGISTERED_MEDIA:
                    issues.append("%s 引用未登记素材 %s" % (os.path.basename(path), enc))
                elif REGISTERED_MEDIA[plain_name] != enc.lstrip("./"):
                    issues.append("%s 的 data-enc 路径与登记不一致：%s" % (os.path.basename(path), enc))
                else:
                    seen.add(plain_name)
        if re.search(r'https?://[^\s"\']+\.(?:jpe?g|png|webp|gif)', raw):
            issues.append("%s 又出现静态图片 URL —— blob 方案下页面不得暴露素材地址"
                          % os.path.basename(path))
        if "/blog/" in raw:
            issues.append("%s 又出现 /blog/ 路径 —— 该迁移已撤销" % os.path.basename(path))

        if os.path.basename(path) == "picks.html":
            if len([t for t in imgs if "data-enc=" in t]) != 2:
                issues.append("picks.html 的 data-enc 截图不是 2 个（站长 2026-11-07 要求）")
            if 'id="shots-grid"' not in raw or 'id="shot-status"' not in raw:
                issues.append("picks.html 缺少解密网格或失败状态位")
            if 'src="./shot-vault.js' not in raw:
                issues.append("picks.html 没有引用 shot-vault.js")
            if raw.count('class="shot-zoom"') != 2:
                issues.append("picks.html 两张原图的点击放大按钮不是 2 个（站长 2026-11-07 要求）")
            if "className='lightbox'" not in raw:
                issues.append("picks.html 缺少 lightbox 点击放大逻辑")
            if "if(!src)return;" not in raw:
                issues.append("picks.html 灯箱没拦住「解密前 src 为空」的点击")
            if "因为帖子下的争论和不少人吵了起来" in raw:
                issues.append("picks.html 又出现旧的错误因果（在瞬间吵了一架导致封号）")
            if "封号是更前面的一桩" not in raw or "不是同一件事" not in raw:
                issues.append("picks.html 缺少 2026-11-07 事实纠正（封号更早 / 私聊是另一件事）")

    if len(seen) != len(REGISTERED_MEDIA):
        issues.append("两张原图未全部接上 data-enc（当前 %d/%d）"
                      % (len(seen), len(REGISTERED_MEDIA)))

    # ⑤ 解密脚本：真用 Web Crypto + createObjectURL，口令两端一致
    vault = os.path.join(root, "shot-vault.js")
    enc_script = os.path.join(root, "scripts", "encrypt-shots.mjs")
    if not os.path.exists(vault) or not os.path.exists(enc_script):
        issues.append("shot-vault.js 或 scripts/encrypt-shots.mjs 缺失")
    else:
        with open(vault, encoding="utf-8") as f:
            js = f.read()
        missing = [m for m in VAULT_REQUIRED if m not in js]
        if missing:
            issues.append("shot-vault.js 缺关键语句（注释里写不算）：" + " / ".join(missing))
        with open(enc_script, encoding="utf-8") as f:
            enc_js = f.read()
        k1 = re.search(r"var PASSPHRASE = '([^']+)'", js)
        k2 = re.search(r"const PASSPHRASE = '([^']+)'", enc_js)
        if not k1 or not k2:
            issues.append("解密脚本或加密脚本里找不到 PASSPHRASE 常量")
        elif k1.group(1) != k2.group(1) or len(k1.group(1)) < 12:
            issues.append("shot-vault.js 与 encrypt-shots.mjs 的解密口令不一致（或太短）")

    notes.append("素材白名单 %d 项，blob 解密渲染 %d/%d；仓库明文素材、静态图片 URL 一律判红"
                 % (len(REGISTERED_MEDIA), len(seen), len(REGISTERED_MEDIA)))
    return issues, notes


def main(argv):
    _utf8()
    args = [a for a in argv[1:] if not a.startswith("--")]
    skip_remote = "--no-remote" in argv
    root = os.getcwd()
    files = set(os.listdir(root))
    pages = args or sorted(f for f in files if f.endswith(".html"))

    results, navsets, footsets = [], {}, {}
    for rel in pages:
        path = rel if os.path.isabs(rel) else os.path.join(root, rel)
        if not os.path.exists(path):
            results.append((os.path.basename(path), ["文件不存在"], []))
            continue
        name, issues, notes, (nav, foot, has_nav, has_foot) = check_page(path, files, not skip_remote)
        results.append((name, issues, notes))
        if has_nav:
            navset = tuple(nav)
            navsets.setdefault(navset, []).append(name)
        if has_foot:
            footsets.setdefault(tuple(foot), []).append(name)

    print("检查页面: %s" % ", ".join(os.path.basename(p) for p in pages))
    print("")
    for name, issues, notes in results:
        print("%-18s %s" % (name, "OK" if not issues else "问题"))
        for i in issues:
            print("    ✗ %s" % i)
        for n in notes:
            print("    · %s" % n)

    # 跨页一致性
    print("")
    if len(navsets) > 1:
        print("✗ 各页导航链接集合不一致：")
        for k, v in navsets.items():
            print("    %s -> %s" % (list(k), ", ".join(v)))
    elif navsets:
        only = list(navsets.values())[0]
        print("✓ 导航一致（%d 页，%d 项）：%s" % (len(only), len(list(navsets)[0]), list(navsets)[0]))
    if len(footsets) > 1:
        print("✗ 各页页脚链接集合不一致：")
        for k, v in footsets.items():
            print("    %s -> %s" % (list(k), ", ".join(v)))
    elif footsets:
        only = list(footsets.values())[0]
        print("✓ 页脚一致（%d 页，%d 项）" % (len(only), len(list(footsets)[0])))

    if ".nojekyll" not in files:
        print("✗ 缺少 .nojekyll（Pages 会走 Jekyll 构建）")
    else:
        print("✓ .nojekyll 存在")

    # 素材规则（站长 2026-11-07 写死，同日纠正为 blob）：README 原文 +
    # 仓库零明文 + 密文容器有效 + data-enc/createObjectURL 链路 +
    # 图片点击放大 + 事实纠正，缺一即判红。
    print("")
    policy_issues, policy_notes = check_asset_policy(root, pages)
    for i in policy_issues:
        print("✗ %s" % i)
    for n in policy_notes:
        print("✓ %s" % n)

    failed = any(i for _, i, _ in results) or len(navsets) > 1 or len(footsets) > 1 \
        or ".nojekyll" not in files or bool(policy_issues)
    print("")
    print("结论: %s" % ("失败 ✗" if failed else "通过 ✓"))
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
