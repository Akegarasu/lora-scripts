# Vue 3 前端重构过程记录

> 原则：页面外形和操作流程尽量保持旧版一致。任何主动改变旧行为的决定，都必须先记录在本文件的“行为差异与待办”中。

## 过程日志

### 2026-07-28：工程基线

- 创建分支 `refactor/vue3-frontend`。
- 完成 API、页面模块、执行时序和用户工作流调研，见 `docs/vue3-frontend-rewrite-research-and-plan.md`。
- 将旧 `frontend/` 完整移动到 `frontendbak/`，保留原 HTML、CSS、JS bundle、恢复源码和来源说明。
- 在原路径创建 Vue 3 + TypeScript + Vite 工程。
- 引入 Vue Router、Pinia、Element Plus；所有开发 API 使用同源路径并由 Vite 代理。
- 安装并固定 Node `22.17.1`，使用 Vite 7 工具链；类型检查和生产构建通过。
- 建立与旧版相近的固定侧栏、训练三栏布局、浅色/暗色主题和移动端抽屉导航。
- 建立旧 `.html` URL、Anima Fast alias、SDXL redirect 和数据集编辑器 alias。
- TensorBoard 与旧 tageditor 继续使用现有后端代理，当前页面已可实际加载 iframe。
- 尚未核对完成的业务页面显示迁移状态，危险按钮保持禁用，不用伪实现替代旧行为。

## 已完成

- [x] 旧前端完整备份到 `frontendbak/`
- [x] Vue 3/TypeScript/Vite 工程与生产构建目录
- [x] Vue Router、Pinia、Element Plus
- [x] 桌面侧栏和移动端导航
- [x] 浅色/暗色主题及旧 storage key `vuepress-color-scheme`
- [x] 旧页面 URL 基线
- [x] TensorBoard `/proxy/tensorboard/` iframe
- [x] 旧 tageditor `/proxy/tageditor/` iframe

## 行为差异与待办

### P0：必须在替换旧版前完成

- [ ] **动态 Schema**：旧版从 `/api/schemas/*` 读取可执行 schema 并通过 Koishi Schema 渲染。新前端尚未实现适配器，所有训练按钮因此保持禁用。
- [ ] **训练完整流程**：恢复 GPU、草稿、历史、预设、导入/导出、参数预览、提交、任务 ID、日志入口和终止行为。
- [ ] **Anima Fast**：迁移安装状态、安装确认、日志 SSE、进度 SSE、刷新恢复、audit 限制和训练 gate。
- [ ] **Tagger**：迁移受控表单、模型预下载、状态轮询、双进度、取消与重置。
- [ ] **数据集编辑器**：迁移扫描、筛选、图库、caption、批量操作、快捷 tag、undo/redo 和会话历史。
- [ ] **任务页**：核对旧 `/task.html` 实际信息后实现任务列表、状态和日志入口。
- [ ] **工具页**：迁移 `/api/run_script`，并修复旧版硬编码 `127.0.0.1:28000` 的行为，改用同源 `/api/run_script`。
- [ ] **配置导出**：旧版直接在浏览器生成 TOML；新版应优先调用后端已有 `/api/config/normalize-for-export`。这是有意行为修正，需验证所有训练类型。
- [ ] **深链部署**：确认 FastAPI `SPAStaticFiles` 对所有 Vue Router history URL 的生产刷新均返回 `index.html`。
- [ ] **现有 Python 静态测试迁移**：旧测试直接断言 `frontend/dist/assets/app.547295de.js` 等 VuePress hash 文件，改名后必然失效。应替换为 Vue 构建、路由和 E2E 测试，不复制旧产物到新 dist 来欺骗测试。

### P1：外形和内容一致性

- [ ] 对照 `frontendbak/dist` 逐页记录桌面与移动截图。
- [ ] 精确迁移训练页字段分组、按钮顺序、提示文案和参数预览。
- [ ] 迁移首页品牌图片或确定新版视觉资产；当前首页保持相同工具型气质，但不是旧首页逐像素复制。
- [ ] 迁移新手指南、参数说明、更新日志和关于页面正文。
- [ ] 迁移设置页的 `ui-configs` 与 TensorBoard 自定义 URL；当前 iframe 固定使用同源代理。
- [ ] 核对 Dreambooth 页面是否继续在导航显示。
- [ ] 核对旧外部 tageditor WebSocket `/proxy/tageditor/queue/join` 的端到端行为。

### P2：工程质量

- [ ] 增加 Vitest、Vue Test Utils 和 API client 单元测试。
- [ ] 增加 Playwright 路由、训练 mock、Tagger、数据集编辑和 iframe smoke 测试。
- [ ] 增加 ESLint/Prettier，并根据仓库规范固定格式。
- [ ] 为 API 响应、任务、Schema、Anima Fast、Tagger 和数据集定义完整 TypeScript 类型。
- [ ] 将当前 CSS 拆分为 token、layout 和 feature 样式；基线阶段暂保持一个文件以减少过早抽象。
- [ ] 增加前端构建到发布/整合包流程，确保干净 clone 可复现。
- [ ] 将 Element Plus 改为按需引入并按页面拆包；当前基线全量引入，生产 JS 约 1 MB，Vite 会给出 chunk size warning。

## 暂定兼容契约

- 生产构建输出：`frontend/dist/`
- 旧版备份：`frontendbak/`
- 后端 API：同源 `/api/*`
- 代理服务：同源 `/proxy/*`
- 主题 storage：`vuepress-color-scheme`
- 训练历史 storage：后续继续兼容 `configs-{type}`
- 训练草稿 storage：后续继续兼容 `configs-{type}-autosave`
- Schema 缓存 storage：待适配器确定后决定是否沿用 `schemas`

## 变更记录规范

后续每个迁移 PR/提交在本文件追加：

1. 迁移的页面或工作流。
2. 对应 API 和 storage key。
3. 与 `frontendbak` 的已知行为差异。
4. 自动化及手工验证结果。
5. 尚未解决的问题和优先级。
