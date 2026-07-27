# SD-Trainer 主 WebUI · 训练参数页视觉打磨（设计交付物）

> **角色**：UI Designer 探索稿  
> **范围**：`http://127.0.0.1:28000` 训练参数类页面（如 `/lora/sd3.html` Anima LoRA 专家模式）  
> **约束**：不改布局结构、不删字段、不改业务流程；实现阶段仅改 `frontend/dist/assets/style.*.css`（+ 可选追加覆盖块）  
> **对照**：`train_monitor` 已落地的暗色科技感 tokens 见 `train_monitor/monitor.css`，本稿提炼**浅色工具 UI** 的对应原则，非强制同色。

---

## 0. 页面结构（保持不变）

```
┌──────────┬────────────────────────────────────┬─────────────────────┐
│ Sidebar  │  schema-container（中栏表单）       │  right-container    │
│ 导航     │  · 训练用模型 / Anima 专用参数…    │  · 页面说明 (h1)    │
│ ~240px   │  · Element Plus 动态表单           │  · 参数预览 (code)  │
│          │  · 分组 h2/h3 + 表单项             │  · 底部按钮区       │
│          │                                    │  max-width: 35%     │
└──────────┴────────────────────────────────────┴─────────────────────┘
```

**DOM 锚点（来自 `lora/sd3.html` SSR）**：

| 区域 | 选择器 |
|------|--------|
| 三栏容器 | `.example-container` |
| 中栏 | `.example-container .schema-container` |
| 右栏 | `.example-container > .right-container` |
| 表单 | `.schema-container form` |
| 右栏说明 | `.right-container .theme-default-content` |
| 参数预览 | `.right-container section .params-section` |
| 预览标题 | `.right-container section header`（「参数预览」） |
| 训练按钮 | `.el-button.max-btn.color-btn` 等 |

---

## 1. 设计原则（与监控页呼应）

| 监控页（暗色） | 主 WebUI（浅色 · 秋叶系） |
|----------------|------------------|
| deep navy 底 + 青色单 accent | **白/浅灰两层**（`--c-bg-soft` 页底 + `--c-bg-mute` 表单白）+ Element 蓝 |
| 面板分层：elevated / surface / inset | 卡片分层：page / panel / inset |
| 无多色渐变进度条 | 无营销渐变；按钮仅用纯色 + 浅底 |
| 信息 Tier：Hero > 指标 > 分析 | Tier：训练控制 > 表单分组 > 预览 > 说明文案 |
| 圆角 lg (12–14px) | 统一 **10–12px** 圆角（比现 4px 明显更「圆润」） |

**气质**：专业训练工具（类似 Linear / Vercel Dashboard 浅色），不是落地页。

---

## 2. Design Tokens（浅色模式 · 建议写入 CSS 覆盖块顶部）

```css
/* SD-Trainer WebUI — suggested override tokens (light) */
:root {
  /* Radius — 核心改动 */
  --sd-radius-sm: 6px;
  --sd-radius-md: 10px;
  --sd-radius-lg: 12px;
  --sd-radius-xl: 14px;
  --sd-radius-pill: 999px;

  /* Element Plus 映射 */
  --el-border-radius-base: var(--sd-radius-md);
  --el-border-radius-small: var(--sd-radius-sm);
  --el-border-radius-round: var(--sd-radius-pill);

  /* Brand（与 monitor 青系同族，压低饱和度适配白底） */
  --sd-accent: #0e7490;
  --sd-accent-hover: #0c6b82;
  --sd-accent-muted: rgba(14, 116, 144, 0.10);
  --sd-accent-border: rgba(14, 116, 144, 0.28);

  /* Surfaces */
  --sd-bg-page: #f4f6f9;
  --sd-bg-panel: #ffffff;
  --sd-bg-form: #f8fafc;           /* 替代现 --c-bg-mute 的生硬灰块 */
  --sd-bg-inset: #f1f5f9;
  --sd-bg-preview: #1e293b;       /* 右栏 code 区保持深色可读 */

  /* Border */
  --sd-border: #e2e8f0;
  --sd-border-strong: #cbd5e1;

  /* Text */
  --sd-text: #0f172a;
  --sd-text-secondary: #475569;
  --sd-text-tertiary: #94a3b8;

  /* Semantic */
  --sd-success: #059669;
  --sd-warning: #d97706;
  --sd-danger: #dc2626;

  /* Shadow（轻量，避免后台感） */
  --sd-shadow-sm: 0 1px 2px rgba(15, 23, 42, 0.06);
  --sd-shadow-panel: 0 1px 0 rgba(255, 255, 255, 0.8) inset,
                     0 8px 24px rgba(15, 23, 42, 0.06);

  /* Spacing */
  --sd-space-1: 4px;
  --sd-space-2: 8px;
  --sd-space-3: 12px;
  --sd-space-4: 16px;
  --sd-space-5: 20px;
  --sd-space-6: 24px;
}
```

**暗色模式（`html.dark`）**：保持 VuePress 暗色变量，仅同步调大 `--el-border-radius-*` 与 accent 色相，勿整页换肤（用户可通过灯泡切换）。

---

## 3. 信息层级

| Tier | 区域 | 视觉处理 |
|------|------|----------|
| **1** | 开始训练 / 终止训练 | 右栏底部固定视觉重心；主按钮实心圆角 pill，终止为 outline 警告色 |
| **2** | 中栏表单分组（h2/h3） | 分组「卡片化」：浅底 + 圆角 + 细分隔，非通栏灰板 |
| **2** | 参数预览 | 深色 inset 圆角容器，等宽字体，像 IDE 侧栏 |
| **3** | 页面 h1 + 介绍段 | 右栏上部，字号适中，muted 色 |
| **3** | 重置/保存/读取/导入 | 次要按钮：outline 或 soft fill，统一高度 36px |
| **4** | 加载训练预设 | 保留 ✨ 文案，改为 **soft accent 条按钮**（非刺眼渐变） |

---

## 4. 分组件规范

### 4.1 中栏 `.schema-container`

**现状**：`background: var(--c-bg-mute)` 通栏平板 + `form { padding: 2rem 3rem }`，直角感强。

**目标**：

- 外背景：`--sd-bg-page`（或保持 mute 但提亮 `#f8fafc`）
- 表单区内：每个 **h2 分组**视为一张 sub-panel：
  - `margin-bottom: var(--sd-space-5)`
  - `padding: var(--sd-space-5) var(--sd-space-6)`
  - `background: var(--sd-bg-panel)`
  - `border: 1px solid var(--sd-border)`
  - `border-radius: var(--sd-radius-lg)`
  - `box-shadow: var(--sd-shadow-sm)`
- **h2 / h3**：去掉 `border-bottom: none` 后的「贴顶横条感」；改为：
  - `font-size: 15px / 14px`，`font-weight: 650`
  - 底部分隔：`1px solid var(--sd-border)`，`padding-bottom: var(--sd-space-3)`，`margin-bottom: var(--sd-space-4)`

### 4.2 表单项（Element Plus）

| 组件 | 规范 |
|------|------|
| `.el-input__wrapper` | `border-radius: var(--sd-radius-md)`；默认边 `--sd-border`；focus：`border-color: var(--sd-accent)` + `box-shadow: 0 0 0 3px var(--sd-accent-muted)` |
| `.el-textarea__inner` | 同上 |
| `.el-select .el-input__wrapper` | 同上 |
| `.el-input-number` | 整体圆角；增减按钮与输入框一体边框 |
| `.el-checkbox` / `.el-radio` | 标签字色 `--sd-text-secondary`；选中 accent `--sd-accent` |
| `.el-switch` | 圆角轨道；on 色 `--sd-accent` |
| `.el-form-item` | `margin-bottom: 18px`；label `--sd-text-secondary` 13px |
| `.el-alert` | `border-radius: var(--sd-radius-md)`；保留现有 margin，略增圆角 |

### 4.3 左栏 `.sidebar`

**现状**：VuePress 默认侧栏，直角高亮条。

**目标**（仅 CSS）：

- 活跃项 `.sidebar-item.active`：`border-radius: var(--sd-radius-md)`；背景 `var(--sd-accent-muted)`；左侧 **3px accent 条**（`border-left` 或 `box-shadow`）
- 子菜单缩进不变；hover 轻底 `var(--sd-bg-inset)`
- 底部 Github / 灯泡区与导航增加 `border-top: 1px solid var(--sd-border)`

### 4.4 右栏 `.right-container`

**现状**：`max-width: 35%`，`border-right: 1px`，`background: var(--code-bg-color)`，分区 header 高 3rem 双横线。

**目标**：

- 整体：`background: var(--sd-bg-panel)`；左边线 `1px solid var(--sd-border)`；可选轻阴影与中间栏分离
- **section header**（参数预览 / Output）：
  - 高度 `44px` → 不必 3rem 生硬双框
  - 改为：`padding: 0 var(--sd-space-5)`；`font-size: 13px`；`font-weight: 650`；`letter-spacing: 0.02em`
  - 仅 **底边** `1px solid var(--sd-border)`，去掉 top border（减少「表格头」感）
- **`.theme-default-content`**：h1 `1.5rem`；段落 `14px` `--sd-text-secondary`；内边距 `var(--sd-space-5)`
- **`.params-section`**：
  - 外层 `margin: var(--sd-space-4) var(--sd-space-5)`
  - `code` 块：`background: var(--sd-bg-preview)`；`border-radius: var(--sd-radius-lg)`；`padding: var(--sd-space-4)`
  - `max-height: 60vh` 保留；滚动条细样式可选

### 4.5 底部按钮 `.max-btn`

**现状**：100% 宽、直角、primary plain 几乎无背景（`.color-btn`）。

**目标**：

| 按钮 | 样式 |
|------|------|
| 开始训练 | 实心 `--sd-accent` 底，白字，`border-radius: var(--sd-radius-md)`，hover 加深；`height: 40px` |
| 终止训练 | outline `--sd-warning` 边 + 浅橙底 8% |
| 全部重置 / 保存 / 读取 / 下载 / 导入 | `background: var(--sd-bg-inset)`；边 `var(--sd-border)`；hover 边加深 |
| ✨加载训练预设✨ | `background: var(--sd-accent-muted)`；边 `var(--sd-accent-border)`；字色 `--sd-accent`（保留 emoji） |

**行间距**：`.el-row` `margin-bottom: var(--sd-space-3)`；列 gutter 保持。

**`.color-btn` 覆盖**：废除 `background: none !important` 的「纯文字」感，改为上表 soft / solid 分级。

---

## 5. ASCII 线框（圆润化后）

```
┌ Sidebar ──────────┬─ Form Canvas ───────────────────────┬─ Right Panel ─────────┐
│ ╭ SD-Trainer      │ ╭──────────────────────────────╮ │ Anima LoRA 训练…      │
│ │ ● Anima LoRA    │ │ 训练用模型                    │ │ 说明段落 (muted)      │
│ │   专家 …        │ │ [rounded inputs………………]       │ ├───────────────────────┤
│ │                 │ ╰──────────────────────────────╯ │ ┌ 参数预览 ─────────┐ │
│ │                 │ ╭──────────────────────────────╮ │ │ { json… }         │ │
│ │                 │ │ Anima 专用参数                │ │ │  dark inset       │ │
│ │                 │ │ [fields…]                     │ │ └───────────────────┘ │
│ │                 │ ╰──────────────────────────────╯ │ [重置][保存][读取]    │
│ ╰ Github 灯泡     │                                  │ [下载][导入]          │
│                   │                                  │ [✨ 加载预设]         │
│                   │                                  │ [开始训练][终止训练]  │
└───────────────────┴──────────────────────────────────┴───────────────────────┘
      ↑ active 圆角 pill                         ↑ 分组卡片圆角      ↑ 预览圆角 + 按钮 pill
```

---

## 6. 色彩克制

1. **全页主色 ≤1 个**（沿用 Element 蓝 `var(--el-color-primary)` / `#409eff`），警告色仅终止训练 / alert。  
2. **禁止**大面积渐变、霓虹 glow（监控页训练态微光不照搬）。  
3. **中栏与右栏**：白/浅灰对比，不用强烈撞色块。  
4. **参数预览**单独深色 inset，形成「代码区」认知，不与表单混色。

---

## 7. 实现指南（给后续 Agent）

### 7.1 推荐做法

在 `frontend/dist/assets/style.874872ce.css` **文件末尾**追加：

```css
/* ========== SD-Trainer UI polish (training params pages) ========== */
/* See frontend/DESIGN-training-params-ui.md */
```

按本文 §2–§4 编写覆盖规则；**优先用现有类名**，避免改 HTML/JS chunk。

### 7.2 必覆盖选择器清单

```text
:root, html.dark:root (radius only for dark)
.example-container .schema-container
.example-container .schema-container form
.example-container .schema-container h2, h3
.example-container > .right-container
.example-container > .right-container section header
.example-container > .right-container .params-section code
.el-input__wrapper, .el-textarea__inner
.el-button.max-btn
.el-button.color-btn.el-button--primary
.el-button.color-btn.el-button--warning
.sidebar .sidebar-item.active
```

### 7.3 不建议改动

- DOM 结构、字段顺序、按钮文案、路由  
- `sd3.html` 等 SSR HTML（除非仅改 class，风险大）  
- JS chunk 内联样式  

### 7.4 验收

```powershell
cd d:\ai\lora-scripts-next
python gui.py
# 浏览器 http://127.0.0.1:28000/lora/sd3.html
# Ctrl+Shift+R；检查 master / flux / sdxl 同类页是否一致
```

**通过标准**：

- [ ] 输入框/按钮/分组卡片可见 **10–12px** 圆角  
- [ ] 中栏分组呈卡片，非一整块灰板  
- [ ] 右栏「参数预览」为圆角深色 code 区  
- [ ] 开始/终止训练按钮层级清晰  
- [ ] 暗色模式不崩（半径生效即可）  

### 7.5 多页面一致性

`example-container` 布局为 **全局** 样式，改一处即作用于 `basic / master / flux / sd3 / sdxl` 等所有训练页。

---

## 8. 可选增强（非本次必须）

- 右栏按钮区 `position: sticky; bottom: 0` + 顶阴影（训练按钮始终可见）— 需测是否遮挡参数预览滚动  
- 表单分组左侧色条（accent 2px）标识「Anima 专用」— 仅 CSS `h2` 选择器  
- 与 `train_monitor` 共用 favicon/字号规范文档  

---

*文档版本：2026-05-21 · 已实现：`style.874872ce.css` 末尾追加 + 源片段 `dist/assets/sd-trainer-ui-polish.css`*
