#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""four-language static builder for dating-data-factcheck.

中文六页是唯一文案源。scripts/i18n-data.tsv 是「中文原文 -> en/jp/ko」字典。
本脚本做两件事：

  python scripts/i18n_build.py --inject   给中文六页幂等注入语言菜单 / CSS / hreflang
  python scripts/i18n_build.py            由中文六页生成 en/ jp/ ko/ 各六页

生成的页面是完整独立 HTML：关掉 JS 也能读，URL 可单独分享，零外部依赖。
中文源页不做运行时翻译，语言切换器只是链接。

约定：
  * 文本节点 / 属性按「strip 后的原文」查字典，逐条替换；未收录的中文文本节点直接判错。
  * <script> / <style> / 注释 / 语言菜单整块保护，脚本块里出现的中文串另做字面替换。
  * 属性里的双引号等做 HTML 转义，避免截断 content="..."。
"""
import html as htmllib
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(ROOT, 'scripts', 'i18n-data.tsv')
PAGES = ['index.html', 'anti-scam.html', 'rules.html', 'expectations.html', 'picks.html', '404.html']
LANGS = ['en', 'jp', 'ko']
HTML_LANG = {'zh': 'zh-CN', 'en': 'en', 'jp': 'ja', 'ko': 'ko'}
LANG_ATTR = {'zh': 'zh', 'en': 'en', 'jp': 'ja', 'ko': 'ko'}
SITE = 'https://dujeongil-galaxy.github.io/dating-data-factcheck/'
OG_LOCALE = {'en': 'en_US', 'jp': 'ja_JP', 'ko': 'ko_KR'}
LONG = {'zh': '中文', 'en': 'English', 'jp': '日本語', 'ko': '한국어'}
SHORT = {'zh': 'CN', 'en': 'EN', 'jp': 'JP', 'ko': 'KR'}
ARIA = {'zh': '语言切换', 'en': 'Language', 'jp': '言語切り替え', 'ko': '언어 전환'}
ORDER = ['zh', 'en', 'jp', 'ko']
ATTR_KEYS = {'title', 'alt', 'aria-label', 'placeholder', 'content', 'value', 'label'}
HAN = re.compile(r'[\u4e00-\u9fff]')
MENU_RE = re.compile(r'<details class="lang-switch"[\s\S]*?</details>')
PROTECT = re.compile(
    r'(<script\b[^>]*>[\s\S]*?</script>|<style\b[^>]*>[\s\S]*?</style>|<!--[\s\S]*?-->)',
    re.I)
TEXT_RE = re.compile(r'>([^<>]*)<')
ATTR_RE = re.compile(r'\b([a-zA-Z-]+)="([^"]*)"')
MISSING = set()


# ---------------------------------------------------------------- dictionary
def load_dict():
    out = {}
    with open(DATA, encoding='utf-8') as f:
        for ln, line in enumerate(f, 1):
            line = line.rstrip('\n')
            if not line.strip():
                continue
            p = line.split('\t')
            if len(p) != 4:
                raise SystemExit('i18n-data.tsv:%d 列数 %d != 4' % (ln, len(p)))
            k, en, jp, ko = p
            if not all(x.strip() for x in p):
                raise SystemExit('i18n-data.tsv:%d 有空列' % ln)
            if k in out:
                raise SystemExit('i18n-data.tsv:%d 重复 key %s' % (ln, k[:30]))
            out[k] = {'en': en, 'jp': jp, 'ko': ko}
    return out


# ---------------------------------------------------------------- UI fragments
CSS = """
  /* lang-switch: 单独的下拉语言菜单，零 JS；手机端显示 CN/EN/JP/KR */
  .lang-switch{position:relative;flex:none;font-size:13px;z-index:60}
  .lang-switch summary{list-style:none;cursor:pointer;display:inline-flex;align-items:center;gap:6px;
    padding:6px 11px;border:1px solid var(--line-strong,var(--line,#e5ded3));border-radius:999px;
    background:#fff;color:var(--ink,#1c1815);white-space:nowrap;user-select:none}
  .lang-switch summary::-webkit-details-marker{display:none}
  .lang-switch summary::marker{content:""}
  .lang-switch[open] .lang-car{transform:rotate(180deg)}
  .lang-car{font-size:10px;opacity:.65;transition:transform .18s}
  .lang-list{position:absolute;right:0;top:calc(100% + 8px);z-index:60;margin:0;padding:6px;
    list-style:none;min-width:136px;background:#fff;border:1px solid var(--line-strong,var(--line,#e5ded3));
    border-radius:12px;box-shadow:0 10px 28px rgba(28,24,21,.14)}
  .lang-list li{margin:0}
  .lang-list a{display:flex;align-items:center;justify-content:space-between;gap:12px;
    padding:7px 10px;border:0;border-radius:8px;background:none;text-decoration:none;
    color:var(--ink,#1c1815);white-space:nowrap;font-size:13px;margin:0}
  .lang-list a:hover{background:var(--paper,#faf7f2)}
  .lang-list a.is-current{font-weight:700;color:var(--accent,#c9502a)}
  .lang-switch .lang-short{display:none}
  /* 英文文案比中日韩长（站名 + 5 项导航合计约 959px，940 容器只有 896px），
     桌面端不收紧就会被 flex 挤成两行、第一行 top 为负往上溢出压住站名。
     只在英文页桌面宽度收紧间距并略放宽 header 容器，其它语言视觉不变。 */
  @media (min-width:761px){
    html[lang="en"] .site-head .wrap{max-width:970px;gap:6px;height:auto;min-height:60px;flex-wrap:wrap}
    html[lang="en"] .site-head .nav{gap:2px}
    html[lang="en"] .site-head .nav a{padding:7px 6px}
    html[lang="en"] .site-head .brand{gap:6px}
  }
  /* 404 页是居中卡片：菜单展开时占文档流、把内容往下顶，任何宽度都不遮挡大号 404 */
  .box > .lang-switch{display:inline-block;margin:0 auto 18px;text-align:left}
  .box > .lang-switch .lang-list{position:static;width:max-content;min-width:136px;
    margin:8px 0 0;box-shadow:none}
  @media (max-width:640px){
    .lang-switch .lang-short{display:inline}
    .lang-switch .lang-long{position:absolute;width:1px;height:1px;padding:0;margin:-1px;
      overflow:hidden;clip:rect(0,0,0,0);white-space:nowrap;border:0}
    .lang-list{min-width:92px}
    /* 320px 下别把站点原有的「菜单」按钮挤成竖排：两个按钮都不许收缩 */
    .site-head .wrap{gap:6px}
    .site-head .brand{flex:1 1 auto;min-width:0}
    .site-head .navwrap{flex:none}
    .site-head .navbtn{flex:none;white-space:nowrap;padding:9px 12px}
    .site-head .lang-switch summary{padding:6px 9px}
    .box > .lang-switch .lang-list{min-width:92px}
  }
  @media (prefers-reduced-motion:reduce){.lang-car{transition:none}}
  /* /lang-switch */
"""

# 去掉最前面的换行，用于「整块替换」；CSS 本身用于首次注入。
CSS_BLOCK = CSS.lstrip('\n')
CSS_HEAD = '/* lang-switch:'
CSS_END = '/* /lang-switch */'
CSS_LEGACY_END = '@media (prefers-reduced-motion:reduce){.lang-car{transition:none}}'


def menu_html(lang, filename, prefix=''):
    """prefix='' 用于根目录中文页，'../' 用于 en/ jp/ ko/ 下的生成页。"""
    rows = []
    for code in ORDER:
        href = prefix + filename if code == 'zh' else prefix + code + '/' + filename
        cur = ' class="is-current" aria-current="page"' if code == lang else ''
        rows.append(
            '        <li><a data-lang-link="%s" href="%s" lang="%s"%s>'
            '<span class="lang-long">%s</span>'
            '<span class="lang-short" aria-hidden="true">%s</span></a></li>'
            % (code, href, LANG_ATTR[code], cur, LONG[code], SHORT[code]))
    # 首行不带缩进：替换时原位置的缩进要保留，否则每次 --inject 都会多叠 4 个空格。
    return (
        '<details class="lang-switch" data-lang-menu>\n'
        '      <summary aria-label="%s"><span class="lang-now">'
        '<span class="lang-long">%s</span>'
        '<span class="lang-short" aria-hidden="true">%s</span></span>'
        '<span class="lang-car" aria-hidden="true">▾</span></summary>\n'
        '      <ul class="lang-list">\n%s\n      </ul>\n'
        '    </details>' % (ARIA[lang], LONG[lang], SHORT[lang], '\n'.join(rows)))


def hreflang_for_page(filename):
    tail = '' if filename == 'index.html' else filename
    lines = []
    for code in ORDER:
        tag = {'zh': 'zh', 'en': 'en', 'jp': 'ja', 'ko': 'ko'}[code]
        path = '' if code == 'zh' else code + '/'
        lines.append('<link rel="alternate" hreflang="%s" href="%s%s%s">'
                     % (tag, SITE, path, tail))
    return '\n'.join(lines)


# ---------------------------------------------------------------- translation
def esc_text(v):
    return v.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')


def esc_attr(v):
    return htmllib.escape(v, quote=True)


def protect(html, d):
    """抽出 script/style/注释与语言菜单，返回 (html, blocks, menu_placeholder)。"""
    blocks = []

    def stash(m):
        blocks.append(m.group(0))
        return '\x00BLK%d\x00' % (len(blocks) - 1)

    html = MENU_RE.sub(lambda m: '\x00LANGMENU\x00', html, count=1)
    html = PROTECT.sub(stash, html)
    return html, blocks


def translate_plain(html, d):
    def tr_text(m):
        t = m.group(1)
        k = t.strip()
        if not k or '\x00BLK' in k or '\x00LANGMENU\x00' in k or not HAN.search(k):
            return m.group(0)
        if k not in d:
            MISSING.add(k)
            return m.group(0)
        lead = t[:len(t) - len(t.lstrip())]
        trail = t[len(t.rstrip()):]
        return '>' + lead + esc_text(d[k][CURLANG]) + trail + '<'

    def tr_attr(m):
        name, val = m.group(1), m.group(2)
        if name not in ATTR_KEYS:
            return m.group(0)
        k = val.strip()
        if not k or not HAN.search(k):
            return m.group(0)
        if k not in d:
            MISSING.add(k)
            return m.group(0)
        return '%s="%s"' % (name, esc_attr(d[k][CURLANG]))

    html = TEXT_RE.sub(tr_text, html)
    html = ATTR_RE.sub(tr_attr, html)
    return html


def restore(html, blocks, d):
    for i, block in enumerate(blocks):
        rep = block
        if block.lower().startswith('<script'):
            # 脚本块里的中文串（灯箱提示等）也换成译文；译文里若带引号会破坏 JS，直接判错。
            for k, vals in d.items():
                if k in rep:
                    v = vals[CURLANG]
                    if "'" in v or '"' in v:
                        raise SystemExit('脚本内译文含引号，会破坏 JS 字符串: ' + k[:40])
                    rep = rep.replace(k, v)
        html = html.replace('\x00BLK%d\x00' % i, rep)
    return html


def page_url(lang, filename):
    tail = '' if filename == 'index.html' else filename
    return SITE + ('' if lang == 'zh' else lang + '/') + tail


def upsert_meta(out, pattern, tag):
    """替换已有的 canonical / og 标签；源页没有就在 </head> 前补一条。

    404.html 中文源页原本完全没有 canonical / og:*，只做 re.sub 会让三个
    译文页缺本地化元数据。生成页一律自带完整 SEO 标签，源页保持不动。
    """
    new, n = re.subn(pattern, lambda _m: tag, out, count=1)
    if n:
        return new
    if '</head>' not in out:
        raise SystemExit('页面缺 </head>，无法补元数据')
    return out.replace('</head>', tag + '\n</head>', 1)


def build_page(src, lang, filename, d):
    global CURLANG
    CURLANG = lang
    MISSING.clear()
    out, blocks = protect(src, d)
    out = translate_plain(out, d)
    out = restore(out, blocks, d)
    if MISSING:
        raise SystemExit('%s %s 未翻译文本 %d 条: %s'
                         % (lang, filename, len(MISSING), list(MISSING)[:4]))
    out = out.replace('\x00LANGMENU\x00', menu_html(lang, filename, '../'))
    out = out.replace('<html lang="zh-CN">', '<html lang="%s">' % HTML_LANG[lang])
    # canonical / og:url / og:locale 一律用该语种的绝对地址；
    # 源页没写（如 404.html）就补，保证 18 张生成页 SEO 标签齐全。
    out = upsert_meta(out, r'<link rel="canonical" href="[^"]*">',
                      '<link rel="canonical" href="%s">' % page_url(lang, filename))
    out = upsert_meta(out, r'<meta property="og:url" content="[^"]*">',
                      '<meta property="og:url" content="%s">' % page_url(lang, filename))
    out = upsert_meta(out, r'<meta property="og:locale" content="[^"]*">',
                      '<meta property="og:locale" content="%s">' % OG_LOCALE[lang])
    # 相对资源与站内链接：生成页在子目录，统一加 ../
    out = re.sub(r'\b(href|src|data-enc)="\./', lambda m: m.group(1) + '="../', out)
    out = re.sub(r'\b(href|src)="assets/', lambda m: m.group(1) + '="../assets/', out)
    out = ('<!DOCTYPE html>\n<!-- Generated by scripts/i18n_build.py. Do not edit by hand. -->\n'
           + out.split('<!DOCTYPE html>\n', 1)[-1])
    return out


# ---------------------------------------------------------------- source injection
def upgrade_css(src):
    """纯函数：把一页的语言菜单 CSS 整块升级成当前常量，并返回新文本。

    CSS 常量改了以后 --inject 必须能把新规则回流到已注入的源页；旧版块没有
    结束标记，按旧末行定位。做成纯函数是为了让校验器能验证幂等性。
    """
    if CSS_HEAD not in src:
        if '</style>' not in src:
            raise SystemExit('没有 </style>')
        return src.replace('</style>', CSS + '</style>', 1)
    pos = src.find(CSS_HEAD)
    line_start = src.rfind('\n', 0, pos) + 1
    endmark = src.find(CSS_END, pos)
    if endmark >= 0:
        block_end = src.find('\n', endmark) + 1
    else:
        legacy = src.find(CSS_LEGACY_END, pos)
        if legacy < 0:
            raise SystemExit('语言菜单 CSS 块边界找不到')
        block_end = src.find('\n', legacy) + 1
    return src[:line_start] + CSS_BLOCK + src[block_end:]


def inject_sources():
    for filename in PAGES:
        path = os.path.join(ROOT, filename)
        src = open(path, encoding='utf-8').read()
        orig = src
        src = upgrade_css(src)
        if 'rel="alternate" hreflang="zh"' not in src:
            m = re.search(r'(<meta name="viewport"[^>]*>\n)', src)
            if not m:
                raise SystemExit(filename + ' 没有 viewport meta')
            src = src[:m.end()] + hreflang_for_page(filename) + '\n' + src[m.end():]
        menu = menu_html('zh', filename)
        if MENU_RE.search(src):
            src = MENU_RE.sub(lambda _m: menu, src, count=1)
            # 历史版本每次注入会多叠 4 个空格，这里一次性把首行缩进规范成 4。
            src = re.sub(r'\n[ \t]*<details class="lang-switch"',
                         '\n    <details class="lang-switch"', src, count=1)
        else:
            m = re.search(r'(</nav>)(\s*</div>\s*</header>)', src)
            if m:
                src = src[:m.end(1)] + '\n    ' + menu + src[m.end(1):]
            else:
                m = re.search(r'(<div class="box">\n)', src)
                if not m:
                    raise SystemExit(filename + ' 找不到菜单插入点')
                src = src[:m.end()] + '    ' + menu + '\n' + src[m.end():]
        if src != orig:
            open(path, 'w', encoding='utf-8', newline='\n').write(src)
            print('inject  ' + filename)


def build_all():
    d = load_dict()
    total = 0
    for lang in LANGS:
        outdir = os.path.join(ROOT, lang)
        os.makedirs(outdir, exist_ok=True)
        for filename in PAGES:
            src = open(os.path.join(ROOT, filename), encoding='utf-8').read()
            out = build_page(src, lang, filename, d)
            with open(os.path.join(outdir, filename), 'w', encoding='utf-8', newline='\n') as f:
                f.write(out)
            total += 1
    print('built %d pages from %d dictionary entries' % (total, len(d)))


CURLANG = 'en'

if __name__ == '__main__':
    if '--inject' in sys.argv:
        inject_sources()
    else:
        build_all()
