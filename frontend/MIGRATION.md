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

### 2026-07-28：基础 API 与任务页

- 新增统一同源 API client，处理 HTTP、网络、JSON、`success/fail/pending/error` 和缺失 data。
- 为版本与任务接口建立 TypeScript 类型和领域 API，不在组件内直接拼装 fetch。
- 侧栏品牌通过 `/api/version` 显示真实后端版本；请求失败时静默回退，不阻塞主界面。
- `/task.html` 已替换为真实任务页：读取 `/api/tasks`、每 2 秒轮询、展示状态/returncode/metadata、打开 `/train-log`，并兼容后端现有 GET 终止接口。
- 行为改进：旧训练页终止操作只取第一个运行任务；新任务页对每个运行任务显示明确 task id 和独立终止按钮。后端当前并发上限仍为 1，因此不改变实际并发语义。
- 验证：Node 22.17.1 下 `npm run typecheck` 与 `npm run build`。

### 2026-07-28：设置与脚本工具

- `/other/settings.html` 恢复旧 `ui-configs` storage key，可保存或重置自定义 TensorBoard URL。
- TensorBoard 页面优先使用自定义 URL，留空时保持 `/proxy/tensorboard/` 同源代理。
- `/lora/tools.html` 接入后端四个白名单脚本，支持参数键值录入和同源 `/api/run_script` 提交。
- 行为修正：删除旧版硬编码 `http://127.0.0.1:28000/api/run_script`，远程访问和自定义端口继续使用当前 origin。
- 安全边界：前端不提供任意脚本路径或 shell 命令，只能选择与后端一致的白名单。

### 2026-07-28：Tagger

- `/tagger.html` 已迁移为 Vue 受控表单，覆盖后端 `TaggerInterrogateRequest` 的全部字段。
- 接入 `/api/tagger/status` 1.2 秒轮询、模型预下载、开始打标、取消和重置。
- 恢复模型下载与图片打标双进度、文件名、计数、错误和 busy 状态按钮切换。
- 行为修正：不再按中文 label 和 Element Plus DOM 反向猜测请求字段，表单模型直接生成类型化请求。

### 2026-07-28：数据集编辑器核心流程

- `/native-tageditor.html` 与 `/dataset-editor.html` 共享 Vue 数据集编辑器。
- 已迁移目录扫描、分类/Caption 筛选、响应式图库、单张 Caption 保存、当前筛选批量追加/删除、撤回和重做。
- 图片继续使用后端返回的安全 `/api/dataset-editor/image` URL，不在浏览器读取本地文件。
- 本组先完成可闭环核心；快捷 tag、多选范围、清理/替换、分页和历史明细仍保留为增强待办。

### 2026-07-28：Anima Fast 安装管理

- `/lora/anima-fast.html` 接入插件状态、2 秒轮询、安装和 repair。
- 安装任务同时连接日志 SSE 与结构化进度 SSE；刷新后可从 status 中的 task id 恢复流。
- ready 前不提供训练提交，ready 后仅导航到训练配置页；训练表单仍受动态 Schema 适配阻塞。
- 保留安装前 NVIDIA GPU、磁盘和独立环境确认，不自动触发大体积下载。

### 2026-07-28：动态 Schema 表单第一阶段

- 接入 `/api/schemas/hashes` 与 `/api/schemas/all`，兼容旧 `schemas` 缓存并按 hash 更新。
- 使用 Schemastery 执行现有 schema，转换为独立表单 AST，支持 object/intersect/union/const、默认值、条件分支和基础约束。
- 训练页已可动态渲染文本、数字、布尔、枚举、数组、textarea、隐藏和禁用字段，并接入系统文件选择、常用路径及多 GPU 字段。
- 恢复旧 `configs-{type}-autosave` 草稿 key，右侧实时显示活动字段序列化后的配置对象。
- 本阶段不启用训练提交；旧 `parseParams` 领域转换、服务端导出规范化和完整训练流程仍是后续 P0。

### 2026-07-28：训练配置与提交闭环

- 迁移旧 `parseParams` 核心转换：基础模式补全、LyCORIS/DyLoRA、DAdapt/Prodigy、分层权重、基础权重、预览参数、浮点值、路径和 GPU id。
- 恢复 `configs-{type}` 历史与 `configs-{type}-autosave` 草稿，接入后端 `/api/presets` 训练预设。
- TOML/JSON 导入先调用 `/api/config/validate-import`，支持训练类型识别和跨页面跳转；导出调用 `/api/config/normalize-for-export` 后生成 TOML。
- 参数面板显示实际提交 TOML，提交前执行 Schema 校验、旧参数冲突检查和确认；成功后展示 task id、同源日志入口和任务页入口。
- Anima Fast 提交前额外调用 `/api/anima-fast/preflight`，后端 `/api/run` 继续执行 feature flag、ready、audit 漂移和最终 preflight gate。

## 已完成

- [x] 旧前端完整备份到 `frontendbak/`
- [x] Vue 3/TypeScript/Vite 工程与生产构建目录
- [x] Vue Router、Pinia、Element Plus
- [x] 桌面侧栏和移动端导航
- [x] 浅色/暗色主题及旧 storage key `vuepress-color-scheme`
- [x] 旧页面 URL 基线
- [x] TensorBoard `/proxy/tensorboard/` iframe
- [x] 旧 tageditor `/proxy/tageditor/` iframe
- [x] 统一 API client 和基础响应类型
- [x] 后端版本读取与侧栏展示
- [x] 真实任务列表、轮询、日志入口和按 task id 终止
- [x] 设置页与旧 `ui-configs` 兼容
- [x] TensorBoard 自定义 URL
- [x] 白名单脚本工具与同源 API
- [x] Tagger 受控表单、预下载、轮询、双进度、取消与重置
- [x] 数据集编辑器扫描、筛选、图库、保存、基础批量与撤回/重做
- [x] Anima Fast 状态、安装/修复、轮询与双 SSE

## 行为差异与待办

### P0：必须在替换旧版前完成

- [x] **动态 Schema 表单适配器**：已完成 Schema 缓存、执行、AST、条件分支、字段渲染、路径选择、GPU 注入和基础校验；训练提交仍受参数转换流程阻塞。
- [x] **训练完整流程**：已恢复 GPU、草稿、历史、预设、导入/导出、参数预览、提交、任务 ID、日志入口和任务页终止行为。
- [x] **Anima Fast 训练约束**：安装 ready 后加载专用 Schema，提交前执行 preflight，最终提交继续受后端 feature flag、audit 和环境漂移 gate 保护。
- [x] **Tagger**：已迁移受控表单、模型预下载、状态轮询、双进度、取消与重置。
- [ ] **数据集编辑器增强**：核心流程已完成；待迁移快捷 tag、多选范围、清理/替换、分页设置和会话历史明细。
- [x] **任务页基础流程**：已实现任务列表、状态、轮询、日志入口与终止；任务详情、日志内嵌和时间信息受后端现有字段限制，后续再增强。
- [x] **工具页基础流程**：已迁移后端白名单脚本与同源 `/api/run_script`；具体脚本参数仍由用户按后端脚本 CLI 填写，后续可按脚本补专用表单。
- [x] **配置导出**：通过后端 `/api/config/normalize-for-export` 规范化后生成可再次导入的 TOML，并由后端现有测试覆盖训练类型适配。
- [ ] **深链部署**：确认 FastAPI `SPAStaticFiles` 对所有 Vue Router history URL 的生产刷新均返回 `index.html`。
- [ ] **现有 Python 静态测试迁移**：旧测试直接断言 `frontend/dist/assets/app.547295de.js` 等 VuePress hash 文件，改名后必然失效。应替换为 Vue 构建、路由和 E2E 测试，不复制旧产物到新 dist 来欺骗测试。

### P1：外形和内容一致性

- [ ] 对照 `frontendbak/dist` 逐页记录桌面与移动截图。
- [ ] 精确迁移训练页字段分组、按钮顺序、提示文案和参数预览。
- [ ] 迁移首页品牌图片或确定新版视觉资产；当前首页保持相同工具型气质，但不是旧首页逐像素复制。
- [ ] 迁移新手指南、参数说明、更新日志和关于页面正文。
- [x] 迁移设置页的 `ui-configs` 与 TensorBoard 自定义 URL。
- [ ] 核对 Dreambooth 页面是否继续在导航显示。
- [ ] 核对旧外部 tageditor WebSocket `/proxy/tageditor/queue/join` 的端到端行为。

### P2：工程质量

- [ ] 增加 Vue Test Utils 和 API client 单元测试；Vitest 与 Schema/训练参数转换单元测试已完成。
- [ ] 增加 Playwright 路由、训练 mock、Tagger、数据集编辑和 iframe smoke 测试。
- [ ] 增加 ESLint/Prettier，并根据仓库规范固定格式。
- [ ] 为 Schema、Anima Fast、Tagger 和数据集定义完整 TypeScript 类型；API 基础响应与任务类型已完成。
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
