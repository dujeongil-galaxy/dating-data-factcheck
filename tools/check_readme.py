#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""检查 README：占位符残留、失效外链、表格列数一致性。

无第三方依赖，只用标准库。发现问题时以非零退出码结束，供 CI 判定失败。
用法：python tools/check_readme.py [README.md ...]
"""
import re
import sys
import unicodedata
import urllib.request
import urllib.error

PLACEHOLDER = [
    r"<user>", r"<repo>", r"your-username", r"your_repo",
    r"\bTODO\b", r"\bFIXME\b", r"\bXXX\b", r"example\.com",
]

# 这些地址是本机/内网示例，不该由 CI 去探测
SKIP_HOST = re.compile(r"(://(127\.0\.0\.1|localhost|0\.0\.0\.0|\[::1\]))", re.I)

def _force_utf8():
    """Windows 控制台默认 GBK，打印 ✓/✗ 会崩；CI 上是 UTF-8 不受影响。"""
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass


UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/124.0 Safari/537.36")


def find_urls(text):
    """收集 markdown 链接、自动链接与裸 URL。"""
    urls = set()
    for m in re.finditer(r"\[[^\]]*\]\(([^)\s]+)", text):
        urls.add(m.group(1))
    for m in re.finditer(r"<(https?://[^>\s]+)>", text):
        urls.add(m.group(1))
    for m in re.finditer(r"https?://[^\s<>)\]\"']+", text):
        urls.add(m.group(0).rstrip(".,;:"))
    return sorted(u for u in urls if u.startswith("http"))


def check_placeholders(text, name):
    # 反引号内的是文档/历史说明（例如变更记录里提到旧的占位模板），不算残留
    text = strip_code_blocks(text)
    bad = []
    for pat in PLACEHOLDER:
        for m in re.finditer(pat, text, re.I):
            line = text[:m.start()].count("\n") + 1
            bad.append((name, line, m.group(0)))
    return bad


def strip_code_blocks(text):
    """去掉围栏代码块与行内代码，避免把示例里的竖线当成表格。"""
    text = re.sub(r"```.*?```", "", text, flags=re.S)
    return re.sub(r"`[^`\n]*`", "", text)


def check_tables(text, name):
    """表头、分隔行、数据行的列数必须一致。"""
    issues = []
    lines = text.split("\n")
    rows, block = [], []
    for i, line in enumerate(lines, 1):
        if line.strip().startswith("|"):
            block.append((i, line))
        else:
            if len(block) >= 2:
                rows.append(block)
            block = []
    if len(block) >= 2:
        rows.append(block)

    for block in rows:
        def cols(row):
            t = row.strip().lstrip("|").rstrip("|")
            return [c.strip() for c in t.split("|")]

        header = cols(block[0][1])
        n = len(header)
        sep_no, sep_line = block[1]
        sep = cols(sep_line)
        if len(sep) != n:
            issues.append((name, sep_no, "分隔行 %d 列 != 表头 %d 列" % (len(sep), n)))
        elif not all(re.fullmatch(r":?-{3,}:?", c) for c in sep if c):
            issues.append((name, sep_no, "分隔行格式不合法: %s" % sep))
        for no, line in block[2:]:
            c = cols(line)
            if len(c) != n:
                issues.append((name, no, "数据行 %d 列 != 表头 %d 列" % (len(c), n)))
    return issues


def probe(url, timeout=25):
    """返回 (是否通过, 说明)。HEAD 不被支持时回退 GET。"""
    for method in ("HEAD", "GET"):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": UA}, method=method)
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                return True, "HTTP %s" % resp.status
        except urllib.error.HTTPError as e:
            # 405/403/501 多半是 HEAD 不被允许，换 GET 再试
            if method == "HEAD" and e.code in (400, 401, 403, 405, 406, 501):
                continue
            return False, "HTTP %s" % e.code
        except Exception as e:
            if method == "HEAD":
                continue
            return False, "%s: %s" % (type(e).__name__, str(e)[:60])
    return False, "未知失败"


def main(argv):
    _force_utf8()
    targets = argv[1:] or ["README.md"]
    ph_bad, tbl_bad, link_bad, link_ok, skipped = [], [], [], [], []

    for path in targets:
        try:
            raw = open(path, encoding="utf-8").read()
        except OSError as e:
            print("!! 读不到 %s: %s" % (path, e))
            return 2

        ph_bad += check_placeholders(raw, path)
        tbl_bad += check_tables(strip_code_blocks(raw), path)

        # 只在非代码文本中找链接：反引号里的示例地址（如说明用的
        # `https://用户名.github.io/仓库名/`）不是可点链接，不该去探测
        for url in find_urls(strip_code_blocks(raw)):
            if SKIP_HOST.search(url):
                skipped.append((path, url))
                continue
            ok, info = probe(url)
            (link_ok if ok else link_bad).append((path, url, info))

    print("检查文件: %s" % ", ".join(targets))
    print("")
    print("占位符/待办标记: %d 处" % len(ph_bad))
    for p, line, hit in ph_bad:
        print("  ✗ %s:%s  命中 %r" % (p, line, hit))
    print("表格列数问题: %d 处" % len(tbl_bad))
    for p, line, msg in tbl_bad:
        print("  ✗ %s:%s  %s" % (p, line, msg))
    print("外链可访问: %d 个通过 / %d 个失败" % (len(link_ok), len(link_bad)))
    for p, url, info in link_ok:
        print("  ✓ %s  (%s)" % (url, info))
    for p, url, info in link_bad:
        print("  ✗ %s  -> %s   [来自 %s]" % (url, info, p))
    if skipped:
        print("跳过（本机/内网示例，不由 CI 探测）: %d 个" % len(skipped))
        for p, url in skipped:
            print("  - %s" % url)

    print("")
    note = ("提示：本检查从 GitHub 执行环境发起，链接可达不代表中国大陆可访问。"
            if link_ok else "")
    if note:
        print(note)

    failed = bool(ph_bad or tbl_bad or link_bad)
    print("结论: %s" % ("失败 ✗" if failed else "通过 ✓"))
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
