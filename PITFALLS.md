# 踩过的坑 · 婚恋数据核查台

> 按时间倒序。每条写清「现象 → 根因 → 怎么修 → 哪条断言防复发」。
> 2026-11-16 一批来自四语构建（`ff1457f`）。

## 第 6 章 · 故障注入的假阳性：改到别的标签去了

**现象**：`SELF-TEST` 明明 15/15 全绿，但定向复核时发现「og:url 指回中文页」这组故障只产生一条「与字典/中文源页不同步」，`og:url` 那条断言根本没被触发。

**根因**：故障用裸 URL 串 `https://…/jp/picks.html` 做 `str.replace(..., 1)`，而这个 URL 在页面里**最先出现在 hreflang 行**，不是 og:url。改的是 hreflang，校验器又没查生成页的 hreflang，于是只有「重建不同步」这个兜底捞住了它。同理「canonical 指向中文页」也改到了 hreflang。只要校验器有逐字节重建比对，任何改动都会被判红，**光看「有报错」等于没验证断言**。

**怎么修**：故障串一律换成完整标签（`<meta property="og:url" content="…">` / `<link rel="canonical" href="…">`），并把 `FAULTS` 从二元组升级成三元组 `(名称, 注入函数, 必须命中的报错子串)`；`main()` 只在 `want in 报错` 时才计数，否则打印 `self-test missed (want …)`。另把「译文页塞回中文原文」的故障从 4 字短词换成字典里的完整中文标题，否则 `visible_text_nodes()` 的 `len(node) >= 8 and node in d` 不会命中。

**防复发**：`i18n_verify.py` 的 `SELF-TEST 25/25 injected faults rejected by their own assertion`；新增断言必须自带能命中自己的故障。

## 第 5 章 · `--inject` 不幂等：每跑一次多叠 4 个空格

**现象**：连跑三次 `python scripts/i18n_build.py --inject`，每次都打印 `inject  index.html`，文件哈希每次都变，`diff` 只显示 `<details class="lang-switch">` 前面多了 4 个空格。

**根因**：`menu_html()` 返回的首行自带 4 个空格缩进，而 `MENU_RE.sub()` 只从 `<details` 开始替换，源页原有的缩进留在原地 → 每替换一次叠一层。

**怎么修**：模板首行改为不带缩进，由首次插入点显式补 `    `；`inject_sources()` 替换既有菜单后用正则把首行缩进归一为 4。同时把 CSS 升级逻辑抽成纯函数 `upgrade_css(src)`，支持把旧版（无结束标记的）CSS 块整块换成当前常量。

**防复发**：`i18n_verify.py::inject_checks()` 断言 `upgrade_css(upgrade_css(src)) == upgrade_css(src)` 且 `upgrade_css(src) == src`（源页不能留有未落地改动），并注入一组「手改 `.lang-list{min-width:92px}`」的故障确认能判红 → `INJECT OK · 6 sources idempotent · 1 injected fault rejected`。

## 第 4 章 · 源页没有 canonical，生成器只替换不补

**现象**：`VERIFY FAILED (3)`，全是 `en/404.html`、`jp/404.html`、`ko/404.html` 的 canonical 错误。

**根因**：根目录 `404.html` 原本既没有 `<link rel="canonical">` 也没有 `og:url` / `og:locale`；`build_page()` 用 `re.sub()` 只替换已存在的标签，没有就什么都不做；而校验器要求每张生成页都有本地化 canonical。给校验器开绿灯是错的——译文页本来就该自带 SEO 元数据。

**怎么修**：新增 `upsert_meta(out, pattern, tag)`，命中就替换、没命中就在 `</head>` 前插入。18 张生成页因此全部有本地化 canonical / og:url / og:locale；中文源页保持原样不动。

**防复发**：`i18n_verify.py` 对三张元数据全部做无条件断言；`generator_checks()` 用没有 canonical 的 404 源页重建三语，验证 9 个标签自动补齐，并注入「源页连 `</head>` 都没有」的故障确认生成器会判错而不是静默吐无元数据页面 → `GENERATOR OK`。

## 第 3 章 · 320px 下新按钮挤坏原有「菜单」按钮

**现象**：真渲染截图里，站点原有的「菜单」按钮被挤成上下两行的「菜 / 单」，胶囊变形为竖椭圆。

**根因**：header 的 `.wrap` 是 `display:flex; justify-content:space-between`，新增的语言按钮是第三个 flex 子项；`.navbtn` 没有 `flex:none` 也没有 `white-space:nowrap`，空间不够时文字先换行。

**怎么修**：注入 CSS 的 ≤640px 块里给 `.site-head .navwrap` / `.site-head .navbtn` 都设 `flex:none`，`.navbtn` 加 `white-space:nowrap` 并收紧 padding，语言按钮 summary 收紧 padding；`.site-head .brand` 才允许收缩。

**防复发**：`i18n_verify.py` 断言三处规则原文存在，并配「撤掉按钮防挤压规则」「撤掉导航容器防收缩规则」两组故障；真渲染 320px 截图肉眼验收。

## 第 2 章 · 404 页浮层下拉压住大号 404

**现象**：404 页菜单插在居中卡片 `.box` 内，展开的浮层遮住「404」最后一位；改成 `position:fixed` 挪到右上角后，320×640 下仍压住数字顶部。

**根因**：404 页 body 用 flex 垂直居中，卡片落在视口中段；任何绝对 / 固定定位的浮层都会向下伸进数字区域。站长对「遮挡文字」零容忍，不能拿「下拉菜单本来就是浮层」当借口。

**怎么修**：404 页专用规则 `.box > .lang-switch .lang-list{position:static;…}`——展开时占文档流、把 404 数字往下顶，任何宽度都不做浮层。桌面与手机实测 `overlaps404Number:false`。

**防复发**：`i18n_verify.py` 断言 `position:static` 原文存在，并配「改回浮层遮挡」故障；CDP 探针计算下拉与 `.n` 的矩形相交，13 个场景全部为 false。

## 第 1 章 · `check_site.py` 只扫根目录，生成页没人管

**现象**：根目录 6 页 `check_site.py --no-remote` 全绿，但 `en/ jp/ ko/` 18 页完全没被检查。

**根因**：`main()` 里 `pages = args or sorted(f for f in os.listdir(root) if f.endswith(".html"))`，只列根目录。直接把子目录页塞给它也不行：它的「导航 / 页脚跨页一致性」比的是中文链接集合，译文页一进来就会互不一致而误判红。

**怎么修**：不改动既有检查器，另写 `scripts/i18n_verify.py` 专管生成页；CI 里与 `check_site.py` 并列挂一步，再加「重建零 diff」兜住手改译文页。

**防复发**：`.github/workflows/readme-check.yml` 的 push 路径包含 `en/**/*.html`、`jp/**/*.html`、`ko/**/*.html`、`scripts/i18n-data.tsv`、`scripts/i18n_build.py`、`scripts/i18n_verify.py`；`.gitattributes` 把换行锁 LF，防 Windows `core.autocrlf` 让 Ubuntu CI 整页假判红。

---

## 记账口径

- 改完代码 → 跑全部校验 → 写 `CHANGELOG.md`（带**真实提交哈希**）→ 新坑写本文件 → `README.md` 扩展约定写长期规则摘要、变更记录写逐批叙述。
- 时间一律用 `git log -1 --format="%h|%ad" --date=format:'%Y-%m-%d %H:%M'`（author date），不要用 `%cd`。
- 文档不许留「待回填」：先提交代码拿真实哈希，再写文档并提交。
- 新增断言必须注入故障验证：不仅要判红，还得是**那条断言自己**判红。
