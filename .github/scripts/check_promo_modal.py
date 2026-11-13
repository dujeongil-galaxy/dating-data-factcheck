#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""检查首页「新站公告」弹窗：5 秒锁定、只能点 × 关闭、备注齐备、缓存号已挂。

站长 2026-11-13 指令：「这次仅设置 5 秒可关闭，但是也是这个逻辑，按下 x
而不是点击空白区域就会关闭弹窗……备注 这是站长的第三个新网站」。

规则不能只写进 README（shuangxiugou 的血泪），所以这里配脚本断言 + CI，
并内置故障注入自检：每次运行都故意把几种回退造出来，确认校验器判红。
只用标准库。用法：python .github/scripts/check_promo_modal.py
"""
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
JS_PATH = os.path.join(ROOT, "promo-modal.js")
INDEX_PATH = os.path.join(ROOT, "index.html")

SCRIPT_TAG = '<script defer src="./promo-modal.js?v=2"></script>'
NOTE = "这是站长的第三个新网站"
NOTE_LINK_HREF = "https://dujeongil-galaxy.github.io/a-reason-for-korea/"
NOTE_LINK_TEXT = "哈韩，也要有一个理由"
READY_LABEL = "点右上角 × 关闭"
LOCK_RE = re.compile(r"var\s+LOCK_MS\s*=\s*5000\s*;")
X_RE = re.compile(r"xEl\.onclick\s*=\s*close\b")
MASK_RE = re.compile(r"pm__mask[^\n]*\.onclick\s*=\s*close")
CLICK_CLOSE_RE = re.compile(r"addEventListener\(\s*['\"]click['\"][\s\S]{0,160}close")
ESC_RE = re.compile(r"addEventListener\(\s*['\"]keydown['\"]|['\"]Escape['\"]")


def strip_comments(js):
    """剥注释再判：注释里写「不绑定」不能把真代码救绿。"""
    code = re.sub(r"/\*[\s\S]*?\*/", "", js)
    return re.sub(r"(?m)^\s*//.*$", "", code)


def validate(js, html):
    errors = []
    if not js.strip():
        return ["promo-modal.js 为空或不存在"]
    if not html.strip():
        return ["index.html 为空或不存在"]
    code = strip_comments(js)

    if not LOCK_RE.search(code):
        errors.append("锁定窗口不是 5 秒（LOCK_MS 必须等于 5000）")
    if not X_RE.search(code):
        errors.append("× 没有绑定 close —— 唯一关闭入口丢了，弹窗会永远关不掉")
    if MASK_RE.search(code) or CLICK_CLOSE_RE.search(code):
        errors.append("遮罩 / 其它元素又绑定了 click → close，点空白就能关")
    if ESC_RE.search(code):
        errors.append("又出现 keydown / Escape 监听，Esc 能关就不是「只能点 ×」")
    if NOTE not in js:
        errors.append("缺少站长要求的备注「%s」" % NOTE)
    if NOTE_LINK_HREF not in js:
        errors.append("备注链接没有指向第三个新网站 a-reason-for-korea")
    if NOTE_LINK_TEXT not in js:
        errors.append("备注链接文字缺失「%s」" % NOTE_LINK_TEXT)
    if READY_LABEL not in js:
        errors.append("到点后没有提示「%s」" % READY_LABEL)
    if SCRIPT_TAG not in html:
        errors.append("index.html 没有挂载 promo-modal.js?v=2")
    if re.search(r"promo-modal\.js\?v=(?!2\b)", html):
        errors.append("index.html 里的 promo-modal.js 缓存号不是 2")
    return errors


def self_test(js, html):
    """故意造错，确认每条断言真的能判红。"""
    x_line = "    xEl.onclick = close;"
    faults = [
        ("锁定改成 3 秒",
         lambda s, h: (s.replace("var LOCK_MS = 5000;", "var LOCK_MS = 3000;"), h)),
        ("遮罩绑回 close",
         lambda s, h: (s.replace(x_line, "    box.querySelector('.pm__mask').onclick = close;\n" + x_line), h)),
        ("Esc 监听回来",
         lambda s, h: (s.replace(x_line, x_line + "\n    document.addEventListener('keydown', function (e) {\n"
                                 "      if (e.key !== 'Escape') return;\n      close();\n    });"), h)),
        ("× 绑定被删",
         lambda s, h: (s.replace(x_line, "    /* x binding removed */"), h)),
        ("备注被删",
         lambda s, h: (s.replace(NOTE, "备注 · 一个新网站"), h)),
        ("备注链接被改去别的站",
         lambda s, h: (s.replace(NOTE_LINK_HREF, "https://example.com/wrong-site"), h)),
        ("到点提示被删",
         lambda s, h: (s.replace(READY_LABEL, "现在可以关闭了"), h)),
        ("缓存号回退",
         lambda s, h: (s, h.replace("promo-modal.js?v=2", "promo-modal.js?v=0"))),
        ("脚本挂载被删",
         lambda s, h: (s, h.replace(SCRIPT_TAG, ""))),
    ]
    caught = 0
    for name, mutate in faults:
        bad_js, bad_html = mutate(js, html)
        if (bad_js, bad_html) == (js, html):
            print("  ! 故障注入无效（no-op）: %s" % name)
            continue
        errs = validate(bad_js, bad_html)
        ok = bool(errs)
        print("  %s %s" % ("✓" if ok else "✗", name))
        caught += 1 if ok else 0
    print("SELF-TEST %d/%d injected faults rejected" % (caught, len(faults)))
    return caught == len(faults)


def main():
    js = ""
    html = ""
    if os.path.exists(JS_PATH):
        with open(JS_PATH, "r", encoding="utf-8") as f:
            js = f.read()
    if os.path.exists(INDEX_PATH):
        with open(INDEX_PATH, "r", encoding="utf-8") as f:
            html = f.read()

    errors = validate(js, html)
    for e in errors:
        print("✗ %s" % e)
    if not errors:
        print("✓ 弹窗规格：5 秒锁定 / 仅 × 可关 / 遮罩与 Esc 不关 / 备注与指向 a-reason-for-korea 的链接齐备 / ?v=2 已挂")

    print("\n--- 故障注入自检 ---")
    selftest_ok = self_test(js, html)

    print("\n结论: %s" % ("通过 ✓" if not errors and selftest_ok else "失败 ✗"))
    return 0 if (not errors and selftest_ok) else 1


if __name__ == "__main__":
    sys.exit(main())
