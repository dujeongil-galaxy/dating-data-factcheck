#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Verify the four-language build of dating-data-factcheck.

Checks are pure functions over a `state` dict, so the same code runs against
deliberately broken copies at the bottom (fault injection). Every new check
must be covered by an injected fault.

Run: python scripts/i18n_verify.py
"""
import copy
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import i18n_build as B  # noqa: E402

MENU_RE = B.MENU_RE
LINK_RE = re.compile(r'<a data-lang-link="([a-z]+)"[^>]*>.*?</a>', re.S)
BLOCK_RE = re.compile(r'(<script\b[^>]*>[\s\S]*?</script>|<style\b[^>]*>[\s\S]*?</style>|<!--[\s\S]*?-->)', re.I)
TEXT_RE = re.compile(r'>([^<>]*)<')
OG_LOCALE = B.OG_LOCALE
REL_ASSET_RE = re.compile(r'\b(href|src|data-enc)="(\./|assets/)')


def load_state():
    d = B.load_dict()
    return {
        'dict': d,
        'sources': {fn: open(os.path.join(B.ROOT, fn), encoding='utf-8').read()
                    for fn in B.PAGES},
        'pages': {
            lang: {fn: (open(os.path.join(B.ROOT, lang, fn), encoding='utf-8').read()
                        if os.path.exists(os.path.join(B.ROOT, lang, fn)) else None)
                   for fn in B.PAGES}
            for lang in B.LANGS
        },
    }


def check_menu(menu, lang, filename, prefix, errors, tag):
    links = LINK_RE.findall(menu)
    if links != B.ORDER:
        errors.append('%s: 语言链接顺序/数量错误 -> %s' % (tag, links))
    for code in B.ORDER:
        m = re.search(r'<a data-lang-link="%s"([^>]*)>(.*?)</a>' % code, menu, re.S)
        if not m:
            errors.append('%s: 缺 %s 链接' % (tag, code))
            continue
        attrs, inner = m.group(1), m.group(2)
        want_href = (prefix + filename) if code == 'zh' else (prefix + code + '/' + filename)
        if 'href="%s"' % want_href not in attrs:
            errors.append('%s: %s href 不是 %s' % (tag, code, want_href))
        if 'lang="%s"' % B.LANG_ATTR[code] not in attrs:
            errors.append('%s: %s 缺 lang 属性' % (tag, code))
        cur = code == lang
        if cur and ('class="is-current"' not in attrs or 'aria-current="page"' not in attrs):
            errors.append('%s: 当前语言 %s 未高亮' % (tag, code))
        if not cur and ('is-current' in attrs or 'aria-current' in attrs):
            errors.append('%s: 非当前语言 %s 被高亮' % (tag, code))
        if '<span class="lang-long">%s</span>' % B.LONG[code] not in inner:
            errors.append('%s: %s 长名缺失' % (tag, code))
        if '<span class="lang-short" aria-hidden="true">%s</span>' % B.SHORT[code] not in inner:
            errors.append('%s: %s 短标签 %s 缺失或未对屏读隐藏' % (tag, code, B.SHORT[code]))
    if 'aria-label="%s"' % B.ARIA[lang] not in menu:
        errors.append('%s: summary aria-label 不是当前语种' % tag)
    if '<span class="lang-long">%s</span>' % B.LONG[lang] not in menu.split('<ul', 1)[0]:
        errors.append('%s: 收起态没有显示当前语种长名' % tag)
    if '<span class="lang-short" aria-hidden="true">%s</span>' % B.SHORT[lang] not in menu.split('<ul', 1)[0]:
        errors.append('%s: 收起态没有当前语种短码' % tag)


def visible_text_nodes(html):
    plain = MENU_RE.sub('', BLOCK_RE.sub('', html))
    return [t.strip() for t in TEXT_RE.findall(plain)
            if t.strip() and B.HAN.search(t) and '\x00' not in t]


def verify(s):
    e = []
    d = s['dict']

    # 1. dictionary
    if len(d) < 460:
        e.append('字典条目不足 460：%d' % len(d))
    for k, vals in d.items():
        if '\t' in k or '\n' in k:
            e.append('字典 key 含分隔符 -> %s' % k[:30])
        if not B.HAN.search(k):
            e.append('字典 key 不含中文 -> %s' % k[:30])
        for lang in B.LANGS:
            v = vals.get(lang, '')
            if not v.strip():
                e.append('字典 %s 缺 %s 译文' % (k[:20], lang))
            elif v.strip() == k.strip():
                e.append('字典 %s 的 %s 译文等于原文' % (k[:20], lang))

    # 2. Chinese source pages
    for fn in B.PAGES:
        src = s['sources'].get(fn) or ''
        tag = 'zh/' + fn
        if not src:
            e.append(tag + ': 中文源页缺失')
            continue
        if '<html lang="zh-CN">' not in src:
            e.append(tag + ': html lang 不是 zh-CN')
        if '/* lang-switch:' not in src:
            e.append(tag + ': 缺语言菜单 CSS')
        if B.CSS_END not in src:
            e.append(tag + ': 缺语言菜单 CSS 块结束标记')
        if '@media (max-width:640px)' not in src:
            e.append(tag + ': 缺手机断点')
        if '.site-head .navbtn{flex:none;white-space:nowrap' not in src:
            e.append(tag + ': 缺 320px 菜单按钮防挤压规则')
        if '.site-head .navwrap{flex:none}' not in src:
            e.append(tag + ': 缺 320px 导航容器防收缩规则')
        if '.box > .lang-switch .lang-list{position:static' not in src:
            e.append(tag + ': 缺 404 页菜单避让规则（展开不遮挡）')
        if '.lang-switch .lang-short{display:none}' not in src:
            e.append(tag + ': 桌面不该显示短码')
        if 'clip:rect(0,0,0,0)' not in src:
            e.append(tag + ': 手机端长名没用 clip 隐藏（屏读会丢）')
        if 'html[lang="en"] .site-head .nav a{padding:7px 6px}' not in src:
            e.append(tag + ': 缺英文 header 导航防溢出规则')
        if src.count('rel="alternate" hreflang=') != 4:
            e.append(tag + ': hreflang 不是 4 条')
        menu = MENU_RE.search(src)
        if not menu:
            e.append(tag + ': 缺语言菜单')
        else:
            check_menu(menu.group(0), 'zh', fn, '', e, tag)

    # 3. generated pages
    for lang in B.LANGS:
        for fn in B.PAGES:
            tag = lang + '/' + fn
            page = s['pages'].get(lang, {}).get(fn)
            if not page:
                e.append(tag + ': 生成页缺失')
                continue
            try:
                want = B.build_page(s['sources'][fn], lang, fn, d)
                if page != want:
                    e.append(tag + ': 与字典/中文源页不同步（需重跑 i18n_build.py）')
            except SystemExit as ex:
                e.append(tag + ': 重建失败 -> %s' % str(ex)[:80])
            if '<html lang="%s">' % B.HTML_LANG[lang] not in page:
                e.append(tag + ': html lang 错误')
            if '<link rel="canonical" href="%s">' % B.page_url(lang, fn) not in page:
                e.append(tag + ': canonical 缺失或指向别处')
            if '<meta property="og:url" content="%s">' % B.page_url(lang, fn) not in page:
                e.append(tag + ': og:url 缺失或没本地化')
            if '<meta property="og:locale" content="%s">' % OG_LOCALE[lang] not in page:
                e.append(tag + ': og:locale 缺失或没本地化')
            bad_rel = REL_ASSET_RE.findall(page)
            if bad_rel:
                e.append(tag + ': 站内资源没加 ../ -> %s' % bad_rel[:2])
            if fn == 'picks.html':
                if 'data-enc="../assets/' not in page:
                    e.append(tag + ': 密文路径没有加 ../')
                if 'src="../shot-vault.js' not in page:
                    e.append(tag + ': 解密脚本路径没有加 ../')
            menu = MENU_RE.search(page)
            if not menu:
                e.append(tag + ': 缺语言菜单')
            else:
                check_menu(menu.group(0), lang, fn, '../', e, tag)
            # 中文原文不得作为文本节点残留在译文页
            for node in visible_text_nodes(page):
                if len(node) >= 8 and node in d:
                    e.append(tag + ': 残留中文原文 -> %s' % node[:30])
                    break
    return e


def script_strings(s, lang):
    """生成页 script 块里不得出现字典中的长中文串。"""
    bad = []
    page = (s['pages'].get(lang, {}).get('picks.html') or '')
    for block in BLOCK_RE.findall(page):
        if block.lower().startswith('<script'):
            for k in s['dict']:
                if len(k) >= 12 and k in block:
                    bad.append(k)
    return bad


# ------------------------------------------------------------------ self-test
def edit_page(s, lang, fn, old, new):
    s['pages'][lang][fn] = s['pages'][lang][fn].replace(old, new, 1)


def edit_page_all(s, lang, fn, old, new):
    s['pages'][lang][fn] = s['pages'][lang][fn].replace(old, new)


def edit_src(s, fn, old, new):
    s['sources'][fn] = s['sources'][fn].replace(old, new, 1)


# 每项 = (故障名, 注入函数, 必须命中的错误子串)。
# 只判「verify 有报错」不够：会被「与中文源页不同步」这个兜底捞住，
# 等于该断言根本没被验证。want 必须是这条断言自己的报错文本。
# 'script-residue:' 是 script_strings() 单独产出的池前缀。
FAULTS = [
    ('源页删掉语言菜单', lambda s: s['sources'].__setitem__(
     'index.html', MENU_RE.sub('', s['sources']['index.html'], count=1)),
     'zh/index.html: 缺语言菜单'),
    ('短标签回退成汉字「中」', lambda s: edit_src(s, 'index.html',
     'aria-hidden="true">CN<', 'aria-hidden="true">中<'),
     'zh/index.html: 收起态没有当前语种短码'),
    ('手机端长名改用 display:none（屏读丢失）', lambda s: edit_src(s, 'index.html',
     'clip:rect(0,0,0,0)', 'clip:unset'),
     'zh/index.html: 手机端长名没用 clip 隐藏'),
    ('桌面默认显示短码', lambda s: edit_src(s, 'rules.html',
     '.lang-switch .lang-short{display:none}', '.lang-switch .lang-short{display:inline}'),
     'zh/rules.html: 桌面不该显示短码'),
    ('hreflang 少一条', lambda s: edit_src(s, 'picks.html',
     '<link rel="alternate" hreflang="ko"', '<link rel="x" hreflang="ko"'),
     'zh/picks.html: hreflang 不是 4 条'),
    ('生成页 lang 回退 zh-CN', lambda s: edit_page(s, 'en', 'index.html',
     '<html lang="en">', '<html lang="zh-CN">'),
     'en/index.html: html lang 错误'),
    ('生成页 canonical 指向中文页', lambda s: edit_page(s, 'jp', 'rules.html',
     '<link rel="canonical" href="https://dujeongil-galaxy.github.io/dating-data-factcheck/jp/rules.html">',
     '<link rel="canonical" href="https://dujeongil-galaxy.github.io/dating-data-factcheck/rules.html">'),
     'jp/rules.html: canonical 缺失或指向别处'),
    ('og:locale 没本地化', lambda s: edit_page(s, 'en', 'index.html',
     'og:locale" content="en_US"', 'og:locale" content="zh_CN"'),
     'en/index.html: og:locale 缺失或没本地化'),
    ('密文路径漏加 ../', lambda s: edit_page(s, 'ko', 'picks.html',
     'data-enc="../assets/', 'data-enc="./assets/'),
     'ko/picks.html: 站内资源没加 ../'),
    ('全部密文路径漏加 ../', lambda s: edit_page_all(s, 'ko', 'picks.html',
     'data-enc="../assets/', 'data-enc="./assets/'),
     'ko/picks.html: 密文路径没有加 ../'),
    ('字典删掉一个 key', lambda s: s['dict'].pop(next(iter(s['dict']))),
     '重建失败'),
    ('译文页塞回中文原文', lambda s: edit_page(s, 'en', 'index.html',
     'What the check found',
     '婚恋数据核查 - 相亲成功率12%真伪 - 胖猫式金钱损失防范'),
     'en/index.html: 残留中文原文'),
    ('当前语言高亮丢失', lambda s: edit_page(s, 'en', 'anti-scam.html',
     '<a data-lang-link="en" href="../en/anti-scam.html" lang="en" class="is-current" aria-current="page">',
     '<a data-lang-link="en" href="../en/anti-scam.html" lang="en">'),
     'en/anti-scam.html: 当前语言 en 未高亮'),
    ('EN 链接指向日语页', lambda s: edit_page(s, 'ko', 'index.html',
     '<a data-lang-link="en" href="../en/index.html"',
     '<a data-lang-link="en" href="../jp/index.html"'),
     'ko/index.html: en href 不是'),
    ('生成页内容被手改', lambda s: s['pages']['jp'].__setitem__(
     '404.html', s['pages']['jp']['404.html'] + '\n<!-- hand edit -->'),
     'jp/404.html: 与字典/中文源页不同步'),
    ('script 内中文串没翻译', lambda s: edit_page(s, 'en', 'picks.html',
     'Click anywhere or press Esc to close', '点击任意处或按 Esc 关闭'),
     'script-residue:'),
    ('404 生成页漏掉 canonical', lambda s: edit_page(s, 'en', '404.html',
     '<link rel="canonical" href="https://dujeongil-galaxy.github.io/dating-data-factcheck/en/404.html">', ''),
     'en/404.html: canonical 缺失或指向别处'),
    ('og:url 指回中文页', lambda s: edit_page(s, 'jp', 'picks.html',
     '<meta property="og:url" content="https://dujeongil-galaxy.github.io/dating-data-factcheck/jp/picks.html">',
     '<meta property="og:url" content="https://dujeongil-galaxy.github.io/dating-data-factcheck/picks.html">'),
     'jp/picks.html: og:url 缺失或没本地化'),
    ('og:locale 整条丢失', lambda s: edit_page(s, 'ko', 'index.html',
     '<meta property="og:locale" content="ko_KR">', ''),
     'ko/index.html: og:locale 缺失或没本地化'),
    ('译文页导航漏加 ../', lambda s: edit_page(s, 'jp', 'index.html',
     'href="../rules.html"', 'href="./rules.html"'),
     'jp/index.html: 站内资源没加 ../'),
    ('译文页引用根目录 assets', lambda s: edit_page(s, 'en', '404.html',
     '<meta charset="UTF-8">', '<meta charset="UTF-8">\n<script src="assets/x.js"></script>'),
     'en/404.html: 站内资源没加 ../'),
    ('撤掉 320px 菜单按钮防挤压规则', lambda s: edit_src(s, 'index.html',
     '.site-head .navbtn{flex:none;white-space:nowrap;padding:9px 12px}',
     '.site-head .navbtn{padding:9px 12px}'),
     'zh/index.html: 缺 320px 菜单按钮防挤压规则'),
    ('撤掉导航容器防收缩规则', lambda s: edit_src(s, 'picks.html',
     '.site-head .navwrap{flex:none}', '.site-head .navwrap{flex:1}'),
     'zh/picks.html: 缺 320px 导航容器防收缩规则'),
    ('404 页菜单改回浮层遮挡', lambda s: edit_src(s, '404.html',
     '.box > .lang-switch .lang-list{position:static',
     '.box > .lang-switch .lang-list{position:absolute'),
     'zh/404.html: 缺 404 页菜单避让规则'),
    ('CSS 块结束标记丢失', lambda s: edit_src(s, 'rules.html',
     B.CSS_END, ''),
     'zh/rules.html: 缺语言菜单 CSS 块结束标记'),
    ('英文导航防溢出规则被撤（会折行压站名）', lambda s: edit_src(s, 'index.html',
     'html[lang="en"] .site-head .nav a{padding:7px 6px}',
     'html[lang="en"] .site-head .nav a{padding:7px 13px}'),
     'zh/index.html: 缺英文 header 导航防溢出规则'),
]


def generator_checks(s):
    """生成器健壮性：中文源页 head 元数据不全时，译文页仍要自动补齐。

    也做一次故障注入：源页连 </head> 都没有时，生成器必须判错而不是
    静默吐出一张没有 canonical 的页面。
    """
    out = []
    src = s['sources']['404.html']
    d = s['dict']
    for lang in B.LANGS:
        built = B.build_page(src, lang, '404.html', d)
        url = B.page_url(lang, '404.html')
        for label, tag in (
                ('canonical', '<link rel="canonical" href="%s">' % url),
                ('og:url', '<meta property="og:url" content="%s">' % url),
                ('og:locale', '<meta property="og:locale" content="%s">' % OG_LOCALE[lang])):
            if tag not in built:
                out.append('%s/404.html 自动补 %s 失败' % (lang, label))
    try:
        B.build_page(src.replace('</head>', ''), 'en', '404.html', d)
        out.append('源页缺 </head> 时生成器没判错')
    except SystemExit:
        pass
    return out


def inject_checks(s):
    """--inject 必须幂等，且源页 CSS 必须已经是当前常量（不留未落地改动）。

    历史坑：菜单模板首行自带缩进，每次注入多叠 4 个空格，文件永远在变。
    """
    out = []
    for fn in B.PAGES:
        src = s['sources'][fn]
        try:
            once = B.upgrade_css(src)
            twice = B.upgrade_css(once)
        except SystemExit as ex:
            out.append(fn + ': --inject 失败 -> %s' % str(ex)[:60])
            continue
        if once != twice:
            out.append(fn + ': --inject 不幂等')
        if once != src:
            out.append(fn + ': --inject 还有未落地改动')
    return out


def main():
    state = load_state()
    errs = verify(state)
    if errs:
        print('VERIFY FAILED (%d)' % len(errs))
        for x in errs[:40]:
            print('  - ' + x)
        return 1
    print('VERIFY OK  ·  %d dictionary entries  ·  6 Chinese sources  ·  18 generated pages  ·  4 languages'
          % len(state['dict']))
    gen_errs = generator_checks(state)
    if gen_errs:
        print('GENERATOR FAILED (%d)' % len(gen_errs))
        for x in gen_errs[:20]:
            print('  - ' + x)
        return 1
    print('GENERATOR OK  ·  9 auto-filled head tags  ·  1 injected fault rejected')
    inj_errs = inject_checks(state)
    if inj_errs:
        print('INJECT FAILED (%d)' % len(inj_errs))
        for x in inj_errs[:20]:
            print('  - ' + x)
        return 1
    broken_inject = copy.deepcopy(state)
    broken_inject['sources']['index.html'] = broken_inject['sources']['index.html'].replace(
        '.lang-list{min-width:92px}', '.lang-list{min-width:99px}', 1)
    if not inject_checks(broken_inject):
        print('  ! inject self-test missed: 手改 CSS 规则没被判红')
        return 1
    print('INJECT OK  ·  6 sources idempotent  ·  1 injected fault rejected')
    caught = 0
    for name, mutate, want in FAULTS:
        broken = copy.deepcopy(state)
        mutate(broken)
        pool = list(verify(broken))
        for lang in B.LANGS:
            pool += ['script-residue:' + k for k in script_strings(broken, lang)]
        if any(want in x for x in pool):
            caught += 1
        else:
            print('  ! self-test missed (want %r): %s' % (want, name))
    print('SELF-TEST %d/%d injected faults rejected by their own assertion'
          % (caught, len(FAULTS)))
    return 0 if caught == len(FAULTS) else 1


if __name__ == '__main__':
    sys.exit(main())
