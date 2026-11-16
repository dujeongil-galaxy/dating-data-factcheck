# 变更记录 · 婚恋数据核查台

> 全量事实记录以本文件为准。`README.md` 的「变更记录」保留按时间倒序的逐批叙述，
> 扩展约定只写长期规则摘要。每条都带**真实提交哈希**；时间取
> `git log -1 --format="%h|%ad" --date=format:'%Y-%m-%d %H:%M'`（author date，不用 `%cd`）。

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
