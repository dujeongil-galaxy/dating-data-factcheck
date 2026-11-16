# 变更记录 · 婚恋数据核查台

> 全量事实记录以本文件为准。`README.md` 的「变更记录」保留按时间倒序的逐批叙述，
> 扩展约定只写长期规则摘要。每条都带**真实提交哈希**；时间取
> `git log -1 --format="%h|%ad" --date=format:'%Y-%m-%d %H:%M'`（author date，不用 `%cd`）。

## 2026-11-16 21:16 · `97cb6ad` · 修复英文页顶部导航折行溢出压站名

站长指令：`https://dujeongil-galaxy.github.io/dating-data-factcheck/en/ 这个版本顶部导航栏已经溢出了，但中、日、韩版本，则不会。修复`。

**根因（定量）**：四语 header 共用 `.wrap{max-width:940px;padding:0 22px}` → 内容区 896px。三块内容（站名 brand + 导航 nav + 语言按钮）自然宽度合计：中文 714px、日文 870px、韩文 826px、英文 **959px**。英文站名 `Dating Data Fact Check`（287px）比中文（214px）长，导航五项 `Source Check / Scam Guide / Rules of Action / Mutual Expectations / Owner's Picks`（557px）也比中文（436px）长，合计超容器 63px。`.site-head .wrap` 在 index / anti-scam / rules 三页写死 `height:60px` 且无 `flex-wrap`，超出部分被 flex 挤压成两行，第一行 `top=-12px` 向上溢出，压住左侧站名第二行 `FACT CHECK`；expectations / picks 两页因原本是 `min-height:60px;flex-wrap:wrap` 故未溢出（header 增高容纳）。中文/日文/韩文都能塞进 896px，单行正常。

**修法**：在 `scripts/i18n_build.py` 的注入 CSS 常量里加一段**只对英文页桌面宽度生效**的规则（`html[lang="en"]` + `@media (min-width:761px)`），改一处回流全部：

```
html[lang="en"] .site-head .wrap{max-width:970px;gap:6px;height:auto;min-height:60px;flex-wrap:wrap}
html[lang="en"] .site-head .nav{gap:2px}
html[lang="en"] .site-head .nav a{padding:7px 6px}
html[lang="en"] .site-head .brand{gap:6px}
```

padding `13px→6px`、nav gap `4px→2px`、容器 `940→970px` 把合计压到 **907px < 926px 容器**（970−44），英文恢复单行；`height:auto;min-height:60px;flex-wrap:wrap` 是兜底——将来文案再变长时导航优雅换行、header 自动增高，不再出现 `top` 为负的向上溢出。其它三语因选择器限定完全不受影响。

**机器强制**：`scripts/i18n_verify.py` 六源页断言新增「必须保留英文 header 防溢出规则」；故障注入 25 → **26 组**，新增「把英文 nav padding 改回 13px」一组，且必须命中自己那条断言（不是被「与生成器不同步」兜底）。`--inject` 幂等自检、生成页逐字节同步自检、生成器健壮性自检仍全绿。

**验证**：
- 无头 Edge + CDP 复测四语 × 六页 × 16 档宽度。修复前英文 index/anti-scam/rules 三页在 1440px 为 `rows=2 / liTops=[-12,32] / 压站名`；修复后 1440px 全部 12 个页面场景 `rows=1 / liTops=[10]`，与中文一致。940px / 860px 下 header 按兜底规则增高到 84.3 / 75.5px，导航仍单行、`liRightMax` 不越界，无横向溢出。
- 计算样式实测：英文 `wrapW=970 / gap=6 / navNat=537 / navGap=2 / nav a padding=7px 6px / brandW=291 / 合计 907`。
- `check_site.py --no-remote` 通过；`check_promo_modal.py` 11/11；`check_readme.py` 通过；`i18n_verify.py` VERIFY / GENERATOR / INJECT / **SELF-TEST 26/26** 全绿。
- 截图 `D:/WorkBuddy-Cache/shots/factcheck-nav/en-1440-head-2x.png`（修复后）、探针数据 `probe.json`。

**范围**：26 files changed（生成器 CSS 常量 1 处 + 校验器 2 处 + 六源页 + 18 生成页回流）。按站长惯例仅本地提交；本仓最后推送状态见最近一条推送记录。踩坑全文见 `PITFALLS.md` 第 7 章。

## 2026-11-16 15:23 · `ff1457f` · 中英日韩四语独立页 + 点击下拉语言菜单

站长指令：`https://dujeongil-galaxy.github.io/dating-data-factcheck/ 去这里，新增中英日韩，注意手机版显示为CN、EN、JP、KR（建议还是单独做一个点击可下拉的菜单）`。
选项确认后按「照搬哈韩站·完整四语」落地：六张中文页分别生成 en / jp / ko 独立译文页，零外部依赖、不用在线机翻。

**交付内容**

| 项 | 结果 |
| --- | --- |
| 中文源页 | 6 张（`index / anti-scam / rules / expectations / picks / 404`），注入语言菜单 CSS、`<details class="lang-switch">`、4 条 hreflang |
| 译文字典 | `scripts/i18n-data.tsv`，465 条中文原文 → en / jp / ko，约 13383 字；覆盖文本节点、`title / meta content / aria-label / alt` 属性、`<script>` 内两条灯箱提示 |
| 生成页 | `en/ jp/ ko/` 各 6 页，共 18 张完整独立 HTML；`<html lang>`、canonical、og:url、og:locale 本地化，站内资源 `../` |
| 构建器 | `scripts/i18n_build.py`：`--inject` 幂等注入源页；默认由源页生成 18 页；`upsert_meta()` 源页缺 canonical / og 时自动补 |
| 校验器 | `scripts/i18n_verify.py`：纯函数 `verify(state)` + 25 组定向故障注入 + 生成器自检 + `--inject` 幂等自检 |
| CI | `.github/workflows/readme-check.yml` 新增两步（跑校验器、重建后 `git diff --exit-code -- en jp ko`），push 路径补四语目录 / 字典 / 构建器 / 校验器 |
| 换行 | 新增 `.gitattributes`，HTML / TSV / PY / YML / MD 锁 LF |

**手机端口径**：桌面显示 `中文 / English / 日本語 / 한국어`，≤640px 显示 `CN / EN / JP / KR`；长名用 `clip:rect(0,0,0,0)` 视觉隐藏但保留给屏读，不用 `display:none`。

**验证结果**

- `check_site.py --no-remote`：6 页全绿，结论「通过 ✓」
- `check_promo_modal.py`：SELF-TEST 11/11，结论「通过 ✓」
- `i18n_verify.py`：VERIFY OK / GENERATOR OK（9 个自动补的 head 标签 + 1 组故障）/ INJECT OK（6 页幂等 + 1 组故障）/ SELF-TEST 25/25
- 重建后 `git diff --exit-code -- en jp ko`：退出码 0
- 无头 Edge + CDP 真渲染 13 场景（1440×900 桌面 / 320×640 手机；中英日韩；五张内容页 + 404）：全部 `overflow:false`，点击下拉生效，手机收起态只显示短码；`overlaps404Number:false`；中文页点 EN → `en/index.html`（`lang=en`、EN 高亮）、译文页点 CN → `index.html`（`lang=zh-CN`、CN 高亮）
- 截图存于本机 `D:/WorkBuddy-Cache/shots/factcheck-i18n/`（缓存，不进仓库）

**文案源规则**：改文案只改中文源页 + `i18n-data.tsv`，随后 `--inject` + 构建并把 18 页一起提交；禁止手改 `en/ jp/ ko/`。

**本批只做本地提交，未推送。**

## 上一批

`82f1682` `fix(modal): 那行改成推广第三个站，不再写「备注这是」` — 详见 `README.md` 变更记录 2026-11-13 条。
