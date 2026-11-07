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

# 站长 2026-11-07 素材链接规则：这两张原图是 11-06 明文留存的历史例外，
# 登记白名单、待迁到 blog 格式链接。放在模块顶部，Parser 与
# check_asset_policy 共用；迁移后仓库内不得再留明文文件。
LEGACY_MEDIA = {
    "soul-2019-comments-1.jpg",
    "soul-2019-comments-2.jpg",
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
            src = a["src"]
            # 白名单里已迁到 blog 格式链接的存量原图，是规则允许的站外素材，
            # 不算「零外部依赖」违规；未登记图片、script、stylesheet 仍一律判红。
            # 不放宽这一条，站长给了 blog 地址也换不上（外链图片会被直接判红）。
            if not (src.startswith("https://") and
                    os.path.basename(urllib.parse.urlparse(src).path) in LEGACY_MEDIA):
                self.external_assets.append("img src=" + src)
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
# 素材链接规则（站长 2026-11-07 写死）
#   「除非我明确表示明文，否则都使用 blog，此规则记录在 GitHub 仓库 README，写死规则」
# 规则不能只写进 README：这里同时锁 ① 规则原文 ② 明文素材白名单
# ③ 页面 img src 只能引用白名单 ④ 两张原图可点击放大 ⑤ 事实纠正不回流。
# 两张 jpg 是站长 2026-11-06 明确要求明文留存的历史例外，登记为待迁移白名单。
# ---------------------------------------------------------------------------
# LEGACY_MEDIA 定义在模块顶部（Parser 也要用），此处不重复定义。
MEDIA_EXT = (".jpg", ".jpeg", ".png", ".webp", ".gif",
             ".mp4", ".mov", ".webm", ".pdf")
ASSET_RULE_MARKERS = (
    "除非站长明确表示",
    "blog 格式链接",
    "不得把素材原始文件明文提交进 GitHub 仓库",
)


def check_asset_policy(root, pages):
    issues, notes = [], []

    readme = os.path.join(root, "README.md")
    if not os.path.exists(readme):
        issues.append("README.md 不存在，素材链接规则无处可查")
    else:
        with open(readme, encoding="utf-8") as f:
            text = f.read()
        missing = [m for m in ASSET_RULE_MARKERS if m not in text]
        if missing:
            issues.append("README 缺少素材链接规则原文：" + " / ".join(missing))

    adir = os.path.join(root, "assets")
    present_legacy = set()
    if os.path.isdir(adir):
        for fn in sorted(os.listdir(adir)):
            if fn.lower().endswith(MEDIA_EXT) and fn not in LEGACY_MEDIA:
                issues.append(
                    "assets/ 出现未登记明文素材 %s —— 新素材须用 blog 格式链接，不得入库" % fn)
            if fn in LEGACY_MEDIA:
                present_legacy.add(fn)
                issues.append(
                    "assets/%s 明文仍在仓库 —— 站长 2026-11-07 要求改用 blog 格式链接后，"
                    "明文路径必须删除" % fn)

    # blog/ 是站长 2026-11-07 指定的素材托管路径（完整 https blog 格式链接）。
    # 该目录只允许两张已登记原图，新增任何素材文件一律判红。
    bdir = os.path.join(root, "blog")
    if os.path.isdir(bdir):
        for fn in sorted(os.listdir(bdir)):
            if fn.lower().endswith(MEDIA_EXT) and fn not in LEGACY_MEDIA:
                issues.append(
                    "blog/ 出现未登记素材 %s —— 新素材须先登记白名单" % fn)

    # 迁移状态机（站长 2026-11-07「不要直接在 GitHub 仓库明文」）：
    #   已迁移：img src 是 https 的 blog 格式链接 + assets/ 明文已删 → 合法
    #   混合态：换了外链却还把明文 jpg 留在 assets/ → 判红
    #   回退态：img src 又写回 ./assets/ 相对路径 → 判红
    blog_refs = set()
    for rel in pages:
        path = rel if os.path.isabs(rel) else os.path.join(root, rel)
        if not os.path.exists(path):
            continue
        with open(path, encoding="utf-8") as f:
            raw = f.read()
        for m in re.finditer(r'<img[^>]+src="([^"]+)"', raw):
            src = m.group(1)
            base = os.path.basename(urllib.parse.urlparse(src).path)
            if src.startswith("./assets/") or src.startswith("assets/"):
                issues.append("%s 又用回 ./assets/ 明文相对路径：%s —— 必须改成 blog 格式链接"
                              % (os.path.basename(path), src))
            elif src.startswith("http://") or src.startswith("https://"):
                if base not in LEGACY_MEDIA:
                    issues.append("%s 引用未登记的站外素材 %s（新素材须先登记白名单）"
                                  % (os.path.basename(path), src))
                if not src.startswith("https://"):
                    issues.append("%s 的 blog 素材链接必须用 https：%s"
                                  % (os.path.basename(path), src))
                if "/blog/" not in src:
                    issues.append("%s 的素材链接不是 blog 格式（路径须含 /blog/）：%s"
                                  % (os.path.basename(path), src))
                if base in LEGACY_MEDIA and src.startswith("https://") and "/blog/" in src:
                    blog_refs.add(base)

        if os.path.basename(path) == "picks.html":
            if raw.count('class="shot-zoom"') != 2:
                issues.append("picks.html 两张原图的点击放大按钮不是 2 个（站长 2026-11-07 要求）")
            if "className='lightbox'" not in raw:
                issues.append("picks.html 缺少 lightbox 点击放大逻辑")
            if "因为帖子下的争论和不少人吵了起来" in raw:
                issues.append("picks.html 又出现旧的错误因果（在瞬间吵了一架导致封号）")
            if "封号是更前面的一桩" not in raw or "不是同一件事" not in raw:
                issues.append("picks.html 缺少 2026-11-07 事实纠正（封号更早 / 私聊是另一件事）")

    for fn in sorted(blog_refs & present_legacy):
        issues.append("%s 已改用 blog 格式链接，但 assets/%s 明文仍留在仓库 —— "
                      "必须删除（站长：不要直接在 GitHub 仓库明文）" % (fn, fn))

    if len(blog_refs) != len(LEGACY_MEDIA):
        issues.append("两张原图未全部改用 blog 格式链接（当前 %d/%d，且 assets/ 明文须清空）"
                      % (len(blog_refs), len(LEGACY_MEDIA)))
    state = "已迁移 %d/%d 项（blog 格式链接）" % (len(blog_refs), len(LEGACY_MEDIA))
    notes.append("素材白名单 %d 项（%s）；新增明文素材一律判红"
                 % (len(LEGACY_MEDIA), state))
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

    # 素材链接规则（站长 2026-11-07 写死）：README 原文 + 明文素材白名单 +
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
