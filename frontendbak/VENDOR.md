# `frontend/dist/` 来源说明

本目录原本是 git submodule，现已 vendored 进主仓库。这份说明用于追溯当前文件从哪来、改了什么、以后怎么同步上游。

## 上游来源

- **仓库**：[`hanamizuki-ai/lora-gui-dist`](https://github.com/hanamizuki-ai/lora-gui-dist)
- **基线 commit**：`20513393bfdd9ee897c538cf68d478c95fcde6c1`（2025-09-08，标题 "update"，目前是 master 的最新且唯一 tip）
- **上游所有者**：花水木 AI（hanamizuki-ai org）—— 秋叶（@Akegarasu）生态下负责 dist 中转的姊妹组织
- **上游来源源码**：秋叶团队的前端源码仓库 `Akegarasu/lora-scripts-frontend`，build 后的产物 push 到 `lora-gui-dist`
- **本仓库写权限**：无。所以本 fork 选择 vendor 而不是继续用 submodule

## 为什么 vendor 而不是 submodule

- 上游 dist 仓库已 7 个月未更新（截至 vendor 时），近似冻结
- 本 fork 需要修改若干 UI 文字以匹配 Anima LoRA 训练流程，没有写权限就只能 vendor
- 主仓库改成 vendored 后，`git clone` 不再需要 `--recurse-submodules`
- dist 总体积 ~1.6 MB，对主仓库无明显负担

## 本仓库对 dist 的 patch 列表

VuePress 是 SSR + hydration 模式：每个页面的 HTML 文件里同时内嵌了首屏 SSR 内容（sidebar、页面 body、`<title>`），加载后由 JS chunk 接管。所以**同一处 UI 文字往往要在 JS 和 HTML 两层都 patch**，否则首屏会闪一下旧文字。本仓库的 patch 分两个 commit：

- [`23337dd`](../../../commit/23337dd)：JS chunk 层的 6 处替换（运行时显示）
- [`1048fbb`](../../../commit/1048fbb)：HTML SSR 层的 21 处替换（首屏显示，避免 SD3 闪烁）

目的是把上游写死的 SD3 字面量替换为 Anima LoRA，让 UI 文字与 `mikazuki/schema/sd3-lora.ts` 已经改写成的 Anima schema 对齐。

### JS chunk 层（commit `23337dd`）

| 文件 | 改前 | 改后 |
|---|---|---|
| `assets/app.547295de.js`（sidebar 配置） | `{"text":"SD3.5","link":"/lora/sd3.md"}` | `{"text":"Anima LoRA","link":"/lora/sd3.md"}` |
| `assets/sd3.html.1a4bf31e.js`（页面 H1） | `SD3 训练 专家模式` | `Anima LoRA 训练 专家模式` |
| `assets/sd3.html.1a4bf31e.js`（副标题） | `SD3 模型 LoRA 训练 专家模式` | `Anima DiT 模型 LoRA 训练 专家模式` |
| `assets/sd3.html.1a4bf31e.js`（介绍段） | `支持 SD3.5 模型的 LoRA 训练` | `Anima DiT 训练入口，使用 Qwen3 + T5 + Anima 专用参数` |
| `assets/sd3.html.1a4bf31e.js`（多余段落） | `别问为什么新手模式不行，问就是你都用 SD3 了还想当新手？` | 删除该段，并把渲染数组 `l=[c,n,d,r]` 同步缩成 `l=[c,n,d]` |
| `assets/sd3.html.eaeb05e1.js`（页面 metadata） | `"title":"SD3 训练 专家模式"` | `"title":"Anima LoRA 训练 专家模式"` |

### HTML SSR 层（commit `1048fbb`）

| 范围 | 改动 | 文件数 / 命中 |
|---|---|---|
| 16 个 HTML 的 sidebar `<a>` 项 | `aria-label="SD3.5"` → `aria-label="Anima LoRA"` | 16 处 |
| 同上 | `<!--[--><!--]--> SD3.5 <!--[--><!--]--></a>` → `<!--[--><!--]--> Anima LoRA <!--[--><!--]--></a>` | 16 处 |
| `lora/sd3.html` 的 `<title>` | `SD3 训练 专家模式 \| SD 训练 UI` → `Anima LoRA 训练 专家模式 \| SD 训练 UI` | 1 处 |
| `lora/sd3.html` H1（`> SD3 训练 专家模式</h1>`） | `> Anima LoRA 训练 专家模式</h1>` | 1 处 |
| `lora/sd3.html` 副标题（`<p>SD3 模型 LoRA ...</p>`） | `<p>Anima DiT 模型 LoRA ...</p>` | 1 处 |
| `lora/sd3.html` 介绍段（`<p>支持 SD3.5 ...</p>`） | `<p>Anima DiT 训练入口，使用 Qwen3 + T5 + Anima 专用参数</p>` | 1 处 |
| `lora/sd3.html` 抖机灵段（`<p>别问为什么...</p>`） | 删除整段 | 1 处 |

### 故意不动的字面量

| 字面量 | 位置 | 原因 |
|---|---|---|
| `/lora/sd3.html`、`/lora/sd3.md` | URL 路由 | SPA 路由 key，改了会让所有指向 sd3 页面的链接 404 |
| `"trainType":"sd3-lora"` | `sd3.html.eaeb05e1.js` frontmatter | 后端 schema 路由 key，对应 `mikazuki/schema/sd3-lora.ts` |
| `id:"sd3-训练-专家模式"`、`href="#sd3-..."` 锚点 | sd3.html、sd3.html.1a4bf31e.js | 不影响显示，保留以兼容历史 anchor 链接 |
| `flux.html`、`index.html`、`assets/index.html.c6ef684b.js` 中的 SD3 字样 | flux 页面文案 / 首页 readme | 跟 Anima 训练入口无关，是上游对其他模型的描述 |

## 怎么重新 vendor 上游（如果上游恢复更新）

```powershell
# 1. 备份当前 dist
Copy-Item frontend\dist _dist_backup -Recurse

# 2. 拉新版 dist
git clone --depth 1 https://github.com/hanamizuki-ai/lora-gui-dist /tmp/new-dist

# 3. 用新版 dist 覆盖（保留 VENDOR.md）
Move-Item frontend\VENDOR.md _vendor_md_backup
Remove-Item frontend\dist -Recurse -Force
Copy-Item /tmp/new-dist frontend\dist -Recurse
Move-Item _vendor_md_backup frontend\VENDOR.md

# 4. 重新应用上面两张表里的 patch（一共 27 处，分两层）：
#    - JS chunk 层 6 处：手工 StrReplace 即可（assets/app.*.js、assets/sd3.html.*.js）
#    - HTML SSR 层 21 处：跨 16 个 HTML 文件，建议写 PowerShell 脚本批量替换
#    具体 pattern 见上面两张表的"改前 / 改后"列。

# 5. 更新本文件的"基线 commit"和上面 patch 列表里的 commit 引用

# 6. 提交
git add frontend/
git commit -m "vendor: refresh frontend/dist from hanamizuki-ai/lora-gui-dist <NEW_SHA>"
```

## 致谢

`frontend/dist/` 中的全部静态资源版权与许可归原作者所有，详见上游 [`hanamizuki-ai/lora-gui-dist`](https://github.com/hanamizuki-ai/lora-gui-dist) 与 [`Akegarasu/lora-scripts-frontend`](https://github.com/Akegarasu/lora-scripts-frontend)。本仓库仅做最小 patch（见上面两张表，共 27 处文字替换）以适配 Anima LoRA 训练入口的命名。
