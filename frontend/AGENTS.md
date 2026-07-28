# Frontend Agent Guide

本文件适用于 `frontend/` 及其子目录，供 AI 编码 Agent 和维护者快速建立上下文。目标是减少重复扫描、错误假设和迁移回归。历史迁移状态见 `MIGRATION.md`，本文件描述当前实现，不是迁移日志。

## 1. 环境要求

- Node.js：`22.17.1`，必须使用 Node 22。版本约束同时记录于 `.nvmrc` 和 `package.json#engines`。
- 包管理器：npm，依赖以 `package-lock.json` 为准。干净环境使用 `npm ci`，不要无故重新生成 lockfile。
- 前端框架：Vue 3.5、TypeScript 5.8、Vite 7、Vue Router 4、Pinia 3、Element Plus 2、Schemastery。
- 后端开发地址：默认 `http://127.0.0.1:28000`。前端只使用同源 `/api/*`、`/proxy/*` 和受控的后端页面路径。
- 开发服务器：默认 `http://localhost:5173`。Vite 代理定义在 `vite.config.ts`。
- 生产输出：`frontend/dist/`，由 Python 后端托管。不要手工修改 `dist/`；它由 `npm run build` 生成且通常不纳入源码改动。
- Windows 发布构建：仓库根目录 `build-scripts/00-build-frontend.ps1` 会执行 Node 检查、`npm ci` 和完整前端构建。

常用命令：

```bash
npm ci
npm run dev
npm run typecheck
npm run lint
npm test
npm run build
npm run check
```

提交前默认执行 `npm run check`。它依次运行类型检查、ESLint、Vitest 和生产构建。

## 2. 首次接手时的最小阅读集

不要从头遍历整个 `src/`。按任务选择以下入口：

| 任务 | 首先阅读 | 需要时再读 |
| --- | --- | --- |
| 路由、页面入口、404 | `src/router.ts` | `src/App.vue`、`src/layouts/AppShell.vue`、`vite.config.ts` |
| API 错误或响应异常 | `src/api/client.ts` | 对应 `src/api/*.ts`、后端具体 route |
| 训练表单不显示/条件错误 | `src/schema/adapter.ts` | `src/components/DynamicSchemaForm.vue`、`SchemaField.vue`、`../mikazuki/schema/*.ts` |
| 训练参数错误 | `src/training/params.ts` | `TrainingPage.vue`、后端 `/api/run` 实现 |
| 预设、导入、导出、提交 | `src/pages/TrainingPage.vue` | `src/api/training.ts`、后端 config API |
| 任务、日志、终止 | `src/pages/TasksPage.vue`、`src/stores/tasks.ts` | `src/api/tasks.ts`、`../mikazuki/app/api.py` |
| Tagger | `src/pages/TaggerPage.vue`、`src/stores/tagger.ts` | `src/api/tagger.ts`、后端 tagger 模块 |
| 数据集编辑器 | `src/pages/DatasetEditorPage.vue` | `src/api/dataset.ts`、`../mikazuki/dataset_editor.py` |
| Element Plus 显示异常 | `src/main.ts` | 对应组件模板、`src/styles/*.css` |
| 样式、字号、响应式 | `src/styles/tokens.css`、`layout.css`、对应 feature CSS | 页面模板 |
| 生产 history 回退 | `../mikazuki/spa.py`、`../mikazuki/app/application.py` | `../tests/test_vue_spa_routes.py` |

优先使用代码索引按符号和调用链查询。已经从索引得到完整源码时，不要再用 grep/read 重读同一文件。只有索引未覆盖、刚修改尚未同步或需要核对非代码资源时才做定向读取。

## 3. 程序结构

```text
frontend/
  src/
    api/          领域 API、请求/响应类型；唯一允许拼 API 路径的前端层
    components/   动态 Schema 表单和字段渲染
    layouts/      全局侧栏、移动导航和页面框架
    pages/        路由页面和页面级工作流
    schema/       Schemastery 源码执行、缓存、AST 适配、条件字段、校验
    stores/       仅跨组件或轮询状态使用 Pinia
    styles/       token、布局和按功能拆分的全局样式
    training/     训练领域参数转换与冲突诊断
    main.ts       应用初始化、Element Plus 按需组件和样式注册
    router.ts     所有 Vue history URL、alias 和 redirect
  public/         原样复制到生产产物的视觉资源
  dist/           Vite 生成目录
  MIGRATION.md    迁移过程、完成项、兼容契约和待办
```

### API 层

- `apiRequest<T>()` 负责网络错误、HTTP 错误、JSON 错误及后端 `success/fail/pending/error` 状态。
- `apiData<T>()` 适合必须返回 `data` 的接口；缺少 `data` 会抛出 `ApiError`。
- 页面不得直接调用 `fetch` 或硬编码 `http://127.0.0.1:28000`。
- 新接口应在 `src/api/` 中定义请求/响应类型，再由页面或 store 调用。
- 后端旧接口可能用 GET 执行 mutation，例如任务终止；不要未经后端同步就擅自“纠正”为 POST。

### 状态层

- 页面私有表单和弹窗状态使用 `ref`/`reactive`，不要为局部状态增加 store。
- Pinia 用于任务轮询、Tagger 等跨组件或持续状态。
- 定时器、`EventSource` 和其他连接必须在组件卸载时释放。

### 路由层

- 路由使用 `createWebHistory()`，生产环境依赖 Python `SPAStaticFiles` 做 history fallback。
- 页面组件必须保持动态 import，避免恢复超大公共 bundle。
- 新增 URL 时同步检查：`router.ts`、侧栏/入口链接、生产 fallback 测试。
- `/assets/*` 缺失必须返回 404，绝不能 fallback 到 SPA HTML。
- `/train-log` 是后端提供的独立 HTML，不是 Vue 页面；开发环境必须由 Vite 代理。

### 样式层

- `tokens.css`：颜色、字体和全局基础 token。
- `layout.css`：应用框架、首页、训练双栏、任务页和响应式布局。
- `features.css`：动态表单、Tagger、数据集、工具和其他共享功能。
- `content-pages.css`、`training-index.css`、`anima-fast.css`：页面族样式。
- 保持现有视觉语言，不引入第二套设计系统。
- 正文通常不应低于 `12px`；长正文建议 `14-16px`、行高 `1.5-1.65`。`9-11px` 只用于真正次要的 badge 或 eyebrow。

## 4. 运行时序

### 应用启动

1. `src/main.ts` 创建 Vue app。
2. 显式注册使用到的 Element Plus 组件、directive 和对应 CSS。
3. 安装 Pinia 和 Router。
4. `App.vue` 根据 route meta 决定是否包裹 `AppShell`。
5. 路由页面按需加载。

### 标准 API 请求

1. 页面或 store 调用领域 API，例如 `trainingApi.run()`。
2. 领域 API 只构造路径、method 和类型化 body。
3. `apiData()`/`apiRequest()` 统一解析后端响应。
4. 页面捕获异常并用 `ElMessage` 给出用户可理解的信息。

### 动态训练表单

1. `TrainingPage` 调用 `loadTrainingSchema(schemaName)`。
2. loader 读取旧兼容 key `localStorage.schemas`。
3. 请求 `/api/schemas/hashes`；hash 变化时再请求 `/api/schemas/all` 并更新缓存。
4. `adapter.ts` 在受控参数环境中执行后端 Schemastery 源码。
5. adapter 将 object/intersect/union/const 转换为独立的 sections/fields AST。
6. `DynamicSchemaForm` 根据 `conditions` 选择活动字段。
7. `SchemaField` 根据字段类型、role 和 options 渲染控件。
8. `serializeModel()` 只输出活动字段。
9. `buildTrainingConfig()` 执行旧 `parseParams` 领域转换并删除 UI-only 字段。
10. 右侧 TOML 预览和提交使用同一个最终 `output`，不要另建一套参数转换。

### 训练提交

1. 前端执行 Schema 必填/范围校验和参数冲突诊断。
2. 用户确认创建后台任务。
3. Anima Fast 先调用 `/api/anima-fast/preflight`。
4. 调用 `/api/run`；后端仍执行最终模型类型、路径、feature flag 和环境校验。
5. 返回 `task_id` 和日志路径。
6. 任务页轮询 `/api/tasks`；日志页 `/train-log` 通过 `/api/train/log/stream/{task_id}` SSE 读取日志。

### 配置兼容

- 历史：`configs-{type}`。
- 自动草稿：`configs-{type}-autosave`。
- Schema 缓存：`schemas`。
- 主题：`vuepress-color-scheme`。
- 设置：`ui-configs`。
- 导入必须先调用 `/api/config/validate-import`。
- 导出必须先调用 `/api/config/normalize-for-export`。
- 不要改变这些 key，除非同时设计持久数据迁移。

## 5. 代码规范

- 使用 Vue `<script setup lang="ts">` 和 Composition API。
- TypeScript 保持 strict；不要用 `any` 绕过后端契约，优先定义领域 interface/type。
- API 路径集中在 `src/api/`，领域转换集中在 `src/training/` 或 `src/schema/`。
- 页面负责协调工作流，不要复制 API 解析、Schema 遍历或训练参数转换。
- 保持最小正确改动；只在逻辑可复用或显著降低复杂度时提取 helper。
- 不新增无依据的兼容分支。涉及已发布 URL、storage key、后端响应或导入文件时才保留兼容性。
- 用户可见 mutation 必须有 busy/disabled 状态和错误反馈。
- 对危险操作使用确认框；取消 (`"cancel"`/`"close"`) 不应显示错误。
- 不使用浏览器本地文件路径替代服务端路径。训练发生在后端机器，路径必须对后端可见。
- 避免对 Vue reactive Proxy 使用 `structuredClone()`。表单模型使用 `cloneFormModel()`/`cloneFormValue()`；Vue Proxy 不能被原生 structured clone。
- 不手改生成文件和缓存：`dist/`、`node_modules/`、`*.tsbuildinfo`。

### Element Plus 按需注册规则

Element Plus 没有全量引入。新增组件时必须同时完成：

1. 在 `main.ts` 从 `element-plus` 导入组件或 directive。
2. 在组件数组中注册，或按 directive 方式注册。
3. 导入对应 `element-plus/es/components/<name>/style/css`。

只注册组件而漏掉 CSS，会出现典型假象：Dialog 标题和关闭按钮像普通文本、MessageBox 出现在页面底部、遮罩缺失、控件无法正常交互。服务式 API（`ElMessage`、`ElMessageBox`）同样需要显式样式导入。

## 6. 已知易踩坑

### Schema union/const

- `const` 字段可能是 union 判别条件，即使没有 `.required()`。
- 条件分支里的判别 `const` 不能覆盖基础 object 中真正可编辑的 enum 字段。
- 修改 `conditionsFrom()`、`collectFields()` 或字段去重时，必须用真实 `lora-master` Schema 回归测试。
- `v2=true` 表示 Stable Diffusion 2.x，不表示 SDXL。SDXL 必须使用 `model_train_type="sdxl-lora"`。

### 远程路径选择

- “浏览”请求 `/api/pick_file`，后端通过 tkinter 在后端机器桌面弹窗。
- 它不浏览访问网页的客户端文件系统；无 GUI、SSH headless 或缺少 tkinter 时不可用。
- “常用路径”使用 `/api/get_files` 在网页内列出后端已知目录，更适合远程部署。
- 所有手工路径也是后端机器路径。

### 开发代理与生产路由

- 新增非 `/api` 后端页面或服务时，检查 `vite.config.ts` 是否需要代理。
- 已知代理包括 `/api`、`/proxy`、`/train-log`、`/font-roboto`。
- 代理配置变更后必须重启 `npm run dev`。
- 开发环境正常不代表生产 history fallback 正常，反之亦然。

### 响应式对象

- `ref({})`、`reactive({})` 和其中的数组会成为 Proxy。
- 原生 `structuredClone(proxy)` 抛出 `DataCloneError`。
- 写入 localStorage 时 `JSON.stringify` 可用；需要内存副本时使用项目提供的表单 clone helper。

### 异步状态

- `finally` 中恢复 loading/submitting。
- 轮询的 silent refresh 不应让整个页面闪烁 loading。
- SSE 刷新恢复依赖后端 status 返回 task id；不要只把 task id 保存在组件内存。

### 后端才是最终安全边界

- 前端校验用于快速反馈，不能替代后端校验。
- Anima Fast 的 feature flag、ready 状态、audit 漂移和 preflight 必须继续由后端 gate。
- 工具页只能提交后端白名单脚本，不允许任意脚本路径或 shell 命令。

## 7. 查找 Bug 的建议流程

1. 先精确记录复现入口、URL、动作、显示错误、Network 请求和 console stack。
2. 判断层级：样式、Vue 状态、领域转换、API client、Vite 代理、后端 route、训练子进程。
3. 从用户动作对应的页面 handler 开始沿调用链向下查，不要先全仓 grep 常见词。
4. 比较“表单 model”“serializeModel 输出”“buildTrainingConfig 输出”“Network body”四个阶段，训练参数丢失通常发生在其中一个边界。
5. API 问题先看浏览器 Network：请求是否发出、URL 是否同源、状态码、JSON `status/message/data`。
6. 视觉组件退化为普通 HTML 时，先检查 Element Plus 样式导入，不要立即重写 CSS。
7. `localhost:5173` 独有的 404，优先检查 Vite proxy；端口 28000 独有的 404，检查后端 route 和 SPA fallback 顺序。
8. 刷新后才出现的问题，检查 localStorage、sessionStorage、Schema hash 缓存和后端会话内 task id。
9. 修复时增加最靠近根因的测试，而不是仅测试页面最终文案。

推荐的最小诊断命令：

```bash
npm run typecheck
npm test -- --run src/schema/adapter.test.ts
npm test -- --run src/training/params.test.ts
npm run build
```

Vitest 脚本本身已经包含 `run`；若附加参数在当前 Vitest 版本不兼容，直接使用 `npx vitest run <file>`。

## 8. 增加功能的建议流程

### 新增普通页面

1. 在 `src/pages/` 创建页面。
2. 在 `router.ts` 使用动态 import 注册 URL 和 title。
3. 如需导航，在 `AppShell.vue` 或入口页增加链接。
4. API 放入对应 `src/api/*.ts`。
5. 样式放入最接近的 feature CSS；不要创建只有几行的页面 CSS。
6. 增加生产 history 深链测试。

### 新增训练模式

1. 后端 `mikazuki/schema/<name>.ts` 定义 Schema。
2. 后端 `/api/schemas/*` 必须能返回该 Schema。
3. 在 `router.ts#trainingRoutes` 增加 `schemaName` 对应路由。
4. 确认 `buildTrainingConfig()` 是否需要该模式专属转换；没有需要时不要新增分支。
5. 后端 trainer mapping、导入识别、导出规范化和 `/api/run` 必须同步支持。
6. 用真实 Schema adapter 测试、参数转换测试和后端提交测试覆盖。

### 新增 Schema 字段类型或 role

1. 在 `FormField` 明确类型和 metadata。
2. 在 adapter 中转换 Schemastery node。
3. 在 `SchemaField.vue` 增加受控组件。
4. 确认默认值、条件激活、校验和序列化行为。
5. 增加 adapter 测试和组件测试。
6. 如使用新 Element Plus 组件，按前述规则注册组件和 CSS。

### 新增后端 API

1. 先确认真实后端 response envelope 和字段可空性。
2. 在 `src/api/` 定义类型化 client。
3. 页面只消费领域 API，不解析 envelope。
4. 为 success、fail、HTTP、网络或 pending 中相关边界增加测试。
5. 若 URL 不在现有 Vite proxy 前缀内，同步更新 proxy。

## 9. 验证矩阵

| 改动 | 最低验证 |
| --- | --- |
| TypeScript/API 类型 | `npm run typecheck`、相关 Vitest |
| Schema adapter/字段 | adapter test、组件 test、`npm run build` |
| 训练参数 | `params.test.ts`、导入/导出或后端提交测试 |
| Element Plus/样式 | `npm run build` + 浏览器手工检查桌面和移动端 |
| 路由/代理 | 开发 URL 手测 + Python SPA route 测试 |
| 数据集 mutation | 前端流程 + `tests/test_dataset_editor_api.py` |
| 发布构建 | `npm run check`，必要时执行 Windows build script 测试 |

前端完整检查通过仍不能证明 Python 托管、SSE 或训练子进程正确。跨边界改动必须运行仓库根目录相关 `pytest`；若环境没有 pytest，应明确记录未执行，而不是声称全部验证通过。

## 10. 修改记录与提交

- 行为迁移、兼容契约或剩余事项变化时更新 `MIGRATION.md`。
- 不要把历史日志中早期“尚未实现”的描述误判为当前待办；以末尾 checklist 和当前源码为准。
- 提交前检查 `git status`、`git diff`、`git diff --check` 和近期 commit 风格。
- 不提交 `.codegraph/`、`node_modules/`、临时日志、用户本地配置或 secret。
- 不回退或覆盖工作区中不属于当前任务的改动。
