# Vue 3 前端重写调研与工作计划

> 调研日期：2026-07-28  
> 调研分支：`refactor/vue3-frontend`  
> 本阶段范围：仅调研和规划，不实现新前端、不修改后端契约。

## 1. 结论摘要

当前 `frontend` 不是可正常开发、构建和测试的前端源码工程。主要 UI 来自上游 VuePress 2 的预编译产物 `frontend/dist`，仓库中没有 `package.json`；仅有从生产 bundle 恢复出的 `frontend/src/layout/layout.js`，通过 `scripts/build_layout.py` 原样复制回 dist。项目又在构建产物上叠加了多批 HTML、压缩 JS、CSS 和原生 JS patch。

因此，继续修补 dist 会持续产生以下问题：

- 无法从源码可靠复现构建产物，HTML SSR 与 hydration JS 经常需要双重修改。
- 页面业务依赖压缩 bundle、动态 `eval` schema、DOM 文案匹配、MutationObserver 和全局 `fetch` 劫持。
- 多个功能已经分散到 VuePress runtime、恢复源码、独立原生 JS 和后端静态页中，模块边界不清晰。
- 自动化测试多为静态字符串断言，缺少可运行的前端单元、组件和端到端测试环境。
- `/api/run_script` 被硬编码为 `http://127.0.0.1:28000`，与可配置 host/port、反向代理和远程访问不兼容。

重写应采用真正的 Vue 3 单页应用工程，以后端现有 FastAPI 契约为边界，以现有 UI 外形、页面 URL 和用户流程为兼容目标。首轮不应同时重构后端 API。

## 2. 调研依据与系统边界

主要依据：

- 后端入口与静态挂载：`mikazuki/app/application.py`
- 主 API：`mikazuki/app/api.py`
- 数据集编辑 API：`mikazuki/dataset_editor.py`
- 代理 API：`mikazuki/app/proxy.py`
- API 响应模型：`mikazuki/app/models.py`
- 前端恢复源码：`frontend/src/layout/layout.js`
- 上游来源：`frontend/VENDOR.md`
- 本项目追加脚本：`frontend/dist/assets/anima-fast-install.js`、`tagger-progress.js`、`dataset-editor.js`、`sd-trainer-brand.js`
- 页面和资源：`frontend/dist/**/*.html`、`frontend/dist/assets/*`

不属于本次 Vue 3 主应用重写的独立服务：

- 训练监控服务 `train_monitor`，由 `/train-monitor` 重定向到默认端口 `6008`。
- TensorBoard 服务，通过 `/proxy/tensorboard/*` 代理。
- 旧标签编辑器服务，通过 `/proxy/tageditor/*` 和 WebSocket 代理。
- 后端训练日志静态查看页 `/train-log`。新前端需要保留入口和调用兼容，但是否将其组件化可在后续单独决定。

## 3. 当前技术与部署架构

### 3.1 当前前端

- VuePress 2 beta 49 预编译多页 HTML，运行时使用 Vue 3 和 Element Plus。
- `frontend/dist` 来源于 `hanamizuki-ai/lora-gui-dist`，本仓库无对应完整源码。
- `frontend/src/layout/layout.js` 是从 bundle 恢复的单文件 canonical source，不是完整项目。
- schema 从后端以 TypeScript/JavaScript 字符串形式下发，浏览器用 `eval` 执行。
- 页面内容由 VuePress frontmatter 决定使用训练表单、iframe、Tagger、设置或工具布局。
- 本地状态主要直接写入 `localStorage`/`sessionStorage`，没有集中状态管理。
- Anima Fast、Tagger 和数据集编辑器依赖额外原生 JS 修补现有 DOM。

### 3.2 当前后端托管

FastAPI 在 `/api` 挂载主 API，先注册特定页面路由，再将 `frontend/dist` 挂载到 `/`。`SPAStaticFiles(..., html=True)` 提供静态页面兜底；中间件还将 VuePress 的 `*.md` 链接重定向到 `*.html`。

后端支持通过 `MIKAZUKI_FRONTEND_DIST` 指向另一份构建产物。新 Vue 3 应继续输出可被该变量或默认 `frontend/dist` 托管的纯静态文件。

### 3.3 建议的新架构边界

- Vue 3 + TypeScript + Vite。
- Vue Router 管理现有 URL 兼容和新页面路由。
- Pinia 仅承载跨页面状态；表单内部状态优先留在 composable/页面组件。
- 统一 `apiClient` 处理 `{status,message,data}`、HTTP 错误和取消。
- schema 适配层先兼容现有后端动态 schema，后续再评估改为声明式 JSON Schema；不要在首轮同时改协议。
- SSE、轮询和代理 iframe 分别封装为独立 service/composable。
- 以源码构建覆盖 `frontend/dist`，不再直接编辑 hash bundle 或 SSR HTML。

## 4. 后端 API 清单与前端对应关系

除特别说明外，API 响应包装为：

```ts
interface APIResponse<T = Record<string, unknown>> {
  status: "success" | "fail" | "pending" | "error"
  message?: string
  data?: T
}
```

### 4.1 配置、schema 与设备

| 方法 | 路径 | 请求/用途 | 当前前端 | Vue 3 归属 |
|---|---|---|---|---|
| POST | `/api/config/validate-import` | `{page_train_type, config}`；校验、拒绝或要求跳转到匹配训练页 | 已调用 | `configApi` + 导入流程 |
| POST | `/api/config/normalize-for-export` | `{page_train_type, config}`；返回规范化配置和 warnings | 后端已提供，当前恢复源码未见调用 | `configApi`；新导出/预览统一使用 |
| GET | `/api/schemas/hashes` | schema 名称与 hash，用于缓存失效 | 已调用 | `schemaStore` |
| GET | `/api/schemas/all` | 完整动态 schema 列表 | 已调用 | `schemaStore` |
| GET | `/api/presets` | 训练预设列表 | 已调用 | `presetApi` |
| GET | `/api/config/saved_params` | 后端配置中的已保存参数 | 当前核心流程未见使用 | 调研实现阶段确认保留入口或废弃 |
| GET | `/api/graphic_cards` | 返回 GPU 列表；初始化期间可能为 `pending` | 已调用，最多重试 3 次 | `deviceApi` |
| GET | `/api/pick_file?picker_type=...` | 系统文件/目录选择器；支持 `folder`、`model-file` | 数据集编辑器使用 `folder` | `filePickerApi` |
| GET | `/api/get_files?pick_type=...` | 列出预设目录中的模型或训练目录 | 由旧动态 schema/runtime 间接使用的可能性高 | `filePickerApi`，迁移时对表单控件验证 |

注意：当前 schema 由浏览器 `eval` 后得到 Koishi Schema 对象。新前端若直接删除该机制，将无法渲染 `mikazuki/schema/*.ts` 定义的字段、默认值、角色控件和说明。首轮必须建立兼容适配器或先把 schema 转换协议独立成一个前置任务。

### 4.2 训练与任务

| 方法 | 路径 | 请求/响应 | 当前前端 | Vue 3 归属 |
|---|---|---|---|---|
| POST | `/api/run` | 完整训练配置，含 `model_train_type`、可选 `gpu_ids`；成功返回 `task_id`、日志 URL、metadata | 已调用 | `trainingApi.start` |
| GET | `/api/tasks` | 所有当前进程任务 | 已调用，用于查找并终止首个运行任务 | `taskStore` |
| GET | `/api/tasks/terminate/{task_id}` | 终止指定任务；虽是有副作用操作但当前契约为 GET | 已调用 | `taskApi.terminate` |
| GET | `/api/train/tasks` | 训练任务列表，与 `/tasks` 近似 | 训练监控/后续 UI 可用 | `taskStore`，实现时确定单一读取入口 |
| GET/SSE | `/api/train/log/stream/{task_id}` | `{text}` 流，结束时 `{done:true}` | 后端日志页/Anima 安装别名使用 | `useTaskLogStream` |
| GET | `/api/train/log/tail/{task_id}?limit=240` | 最近日志行、总数、完成状态 | 监控用途 | 日志恢复/降级读取 |
| GET | `/train-log?task_id=...` | 后端托管的全屏日志页 | `/api/run` 返回该地址 | 保留外链或 iframe |
| GET | `/train-monitor` | 重定向到独立监控服务 | 导航入口 | 保留外链 |

训练提交关键后端约束：

- 标准训练要求 `train_data_dir` 和 `pretrained_model_name_or_path` 非空并存在。
- 后端按 `model_train_type` 选择训练器，并规范化 prompt、Anima 默认值、路径、类型和 TOML。
- 同时只允许一个运行任务；创建失败返回结构化错误。
- Anima Fast 在 `/api/run` 内还有插件启用、ready、环境审计和 preflight gate。

### 4.3 Anima Fast 插件

| 方法 | 路径 | 请求/用途 | 当前前端 | Vue 3 归属 |
|---|---|---|---|---|
| GET | `/api/plugins/anima-lora/status` | 插件状态、feature flag、audit facts、runtime 路径 | 页面进入及每 2 秒轮询 | `animaFastStore` |
| POST | `/api/plugins/anima-lora/preflight` | 训练配置预检 | 当前补丁未直接调用 | 提交前可显式展示 |
| POST | `/api/plugins/anima-lora/dry-run` | 生成适配后 TOML 和 warnings，不启动训练 | 当前补丁未直接调用 | 高级预览/诊断 |
| POST | `/api/plugins/anima-lora/install` | `{dry_run, source_root?, source_commit?}`；启动安装任务 | 已调用 `{dry_run:false}` | 安装向导 |
| POST | `/api/plugins/anima-lora/repair` | 同 install，强制修复 | 后端已有，当前页面未见入口 | 安装向导 |
| POST | `/api/plugins/anima-lora/uninstall` | 卸载插件 | 后端已有，当前页面未见入口 | 管理入口，需二次确认 |
| GET/SSE | `/api/plugins/anima-lora/install/log/stream/{task_id}` | 安装日志，实际复用训练日志流 | 已调用 | `useInstallLogStream` |
| GET/SSE | `/api/plugins/anima-lora/install/progress/stream/{task_id}` | 结构化安装进度 | 已调用 | `useInstallProgressStream` |
| POST | `/api/anima-fast/preflight` | preflight 兼容别名 | 未见当前调用 | 仅兼容，不作为新调用首选 |
| POST | `/api/anima-fast/dry-run` | dry-run 兼容别名 | 未见当前调用 | 仅兼容，不作为新调用首选 |

当前补丁还会在全局重写 `window.fetch`，拦截 `/api/run` 并修正不兼容参数组合。Vue 3 中必须将这些规则移入显式的 Anima Fast 表单校验/规范化层，禁止继续全局劫持：

- `flash` 依赖 `flash_attn`。
- `Automagic` 依赖 `optimum.quanto`。
- cache 选项与 `skip_cache_check` 冲突时需阻止。
- `compile_mode=full` 与 gradient checkpointing 冲突时改为 `blocks` 或禁止组合。

### 4.4 Tagger

| 方法 | 路径 | 请求/用途 | 当前前端 | Vue 3 归属 |
|---|---|---|---|---|
| GET | `/api/tagger/status` | 完整任务快照：phase、下载和打标进度等 | 每 1200ms 轮询，忙时 300ms burst | `taggerStore` |
| GET | `/api/tagger/download-status` | 下载相关状态子集 | 当前未见调用 | 可不调用，保留后端兼容 |
| POST | `/api/tagger/prefetch` | `{interrogator_model, download_endpoint}` | 已调用 | `taggerApi.prefetch` |
| POST | `/api/interrogate` | `TaggerInterrogateRequest` | 已调用 | `taggerApi.start` |
| POST | `/api/tagger/cancel` | 取消下载或打标任务 | 已调用 | `taggerApi.cancel` |
| POST | `/api/tagger/reset` | 忙时请求取消并重置状态 | 已调用 | `taggerApi.reset` |

`TaggerInterrogateRequest` 字段包括：`path`、`interrogator_model`、两个 threshold、rating/model tag 开关、附加/排除 tag、转义、递归、冲突策略、下划线替换、下载源及替换排除项。

### 4.5 数据集标签编辑器

| 方法 | 路径 | 请求/用途 | 当前前端 | Vue 3 归属 |
|---|---|---|---|---|
| POST | `/api/dataset-editor/scan` | `{path}`；扫描图片、caption、tag、分类并返回 `image_url` | 已调用 | `datasetEditorStore.scan` |
| GET | `/api/dataset-editor/image?root=...&image=...` | 安全读取数据集图片 | 图片卡片与预览直接使用 | 图片 URL |
| POST | `/api/dataset-editor/caption` | `{root,image,caption}`；保存单个 caption | 已调用 | `saveCaption` |
| POST | `/api/dataset-editor/batch` | `{root,images,append,remove,replace,sort,clean,underscore_to_space,strip_escape_chars}` | 批量编辑、清理、追加触发词 | `batchEdit` |
| POST | `/api/dataset-editor/undo` | `{root}`；撤回会话内上次已保存操作 | 已调用 | `undo` |
| POST | `/api/dataset-editor/redo` | `{root}`；重做 | 已调用 | `redo` |
| POST | `/api/dataset-editor/history` | `{root}`；返回撤回/重做能力与最近 20 条变更 | 已调用 | `history` |

撤回/重做栈只存在于后端进程内存中，以数据集 root 隔离；重启服务后历史消失。新 UI 不应暗示它是持久历史。

### 4.6 工具、代理与系统信息

| 方法 | 路径 | 请求/用途 | 当前前端 | Vue 3 归属 |
|---|---|---|---|---|
| POST | `/api/run_script` | `{script_name, ...args}`；后台运行白名单脚本 | 已调用，但 URL 硬编码 localhost | `toolsApi.run`，必须改同源相对路径 |
| GET | `/api/check_update` | 返回缓存或即时版本更新检查 | 后端已有；当前主流程未确认入口 | 关于/更新页 |
| GET | `/api/version` | 本地版本 | 品牌脚本调用 | `appStore` |
| GET/POST | `/proxy/tensorboard/{path}` | TensorBoard 反向代理 | iframe | TensorBoard 页 |
| GET/POST | `/font-roboto/{path}` | TensorBoard 字体资源代理 | iframe 内部 | 无直接 UI 调用 |
| GET/POST | `/proxy/tageditor/{path}` | 旧标签编辑器 HTTP 代理 | iframe | 旧编辑器页 |
| WS | `/proxy/tageditor/queue/join` | 旧标签编辑器 WebSocket 代理 | 由 iframe 内应用使用 | 不自行重写协议 |

## 5. 当前页面与模块清单

### 5.1 应保留的用户页面

| 页面/路由 | 主要功能 | 重写策略 |
|---|---|---|
| `/` | 首页、训练与工具入口、版本品牌 | Vue 首页 |
| `/lora/index.html` | LoRA 模式入口 | Vue 路由，保留旧 URL |
| `/lora/basic.html` | LoRA 新手训练 | 共享训练页 + basic schema |
| `/lora/master.html` | Stable Diffusion LoRA 专家训练 | 共享训练页 + master schema |
| `/lora/flux.html` | Flux LoRA 训练 | 共享训练页 + flux schema |
| `/lora/sd3.html` | Anima LoRA 专家训练，URL 因兼容继续保留 | 共享训练页 + `sd3-lora` schema |
| `/lora/anima-fast.html` | Anima Fast 安装和训练 | 共享训练页 + 插件管理模块 |
| `/lora/anima-finetune.html` | Anima 全量微调 | 共享训练页 + finetune schema |
| `/dreambooth/index.html` | Dreambooth 训练 | 共享训练页 + dreambooth schema |
| `/lora/params.html` | 参数调节说明 | 静态/文档型 Vue 页面 |
| `/lora/tools.html` | 白名单脚本工具 | 工具表单页 |
| `/tagger.html` | 模型预下载、图片自动打标、进度和取消 | 独立 Tagger 页面 |
| `/native-tageditor.html`、`/dataset-editor.html` | 原生数据集 caption 编辑 | 合并为一个 Vue 数据集编辑页面，旧 URL alias |
| `/tageditor.html` | 旧外部标签编辑器 | 代理 iframe 页面 |
| `/tensorboard.html` | TensorBoard | 代理 iframe 页面 |
| `/task.html` | 任务查看 | Vue 任务页；需补齐现有行为基线 |
| `/other/settings.html` | TensorBoard URL 等本地设置 | Vue 设置页 |
| `/other/about.html`、`/other/changelog.html`、`/help/guide.html` | 关于、更新日志、使用指南 | 静态内容组件/Markdown 内容 |

`/lora/sdxl.html` 目前由后端重定向到 `/lora/master.html`，必须保持。

### 5.2 建议的 Vue 3 模块

```text
src/
  app/                 # app bootstrap、router、providers
  api/                 # apiClient 与按领域拆分的 API
  layouts/             # AppShell、训练三栏布局、iframe 布局
  pages/               # 首页、训练、Tagger、数据集编辑、任务、设置、文档页
  features/
    schema-form/       # schema 适配与动态控件
    training/          # 参数、预览、历史、预设、提交和终止
    anima-fast/        # 状态、安装、审计、约束和 SSE
    tagger/            # 表单、轮询、进度、取消
    dataset-editor/    # 扫描、筛选、图库、caption、批量、历史
    tasks/             # 任务列表、状态、日志入口
    integrations/      # TensorBoard/旧 tageditor iframe
  stores/              # 仅跨页面状态
  composables/         # polling、SSE、storage、dirty guard
  types/               # API 与 schema 类型
  styles/              # 从现有视觉 token 迁移的全局样式
```

## 6. 当前执行时序

### 6.1 应用启动与 schema

```text
浏览器加载 HTML
  -> 根据 localStorage 的 vuepress-color-scheme 设置暗色类
  -> VuePress app hydration
  -> layout beforeMount
     -> 暴露 window.__MIKAZUKI__ 共享 prompt 常量
     -> localStorage.schemas 载入 schema 缓存
     -> GET /api/schemas/hashes
     -> hash 不一致时 GET /api/schemas/all
     -> 写回 localStorage.schemas
  -> 根据 page frontmatter 选择页面组件
```

风险：第一次没有本地 schema 时，当前逻辑仍先请求 hash，只有检测到差异才拉全量；动态 schema 依赖 `eval` 和全局 `Schema`/`UpdateSchema`。

### 6.2 训练页初始化

```text
TrainingPage beforeMount
  -> 从 frontmatter 取 trainType
  -> 从 SchemaManager 取得 schema
  -> 首次请求 GET /api/graphic_cards（pending 时重试）
  -> 多 GPU 时动态追加 gpu_ids 字段
TrainingPage mounted
  -> 载入 localStorage configs-{type} 历史列表
  -> 若 sessionStorage 有 mikazuki-pending-import
     -> POST /api/config/validate-import
     -> 全量应用导入配置
  -> 恢复 localStorage configs-{type}-autosave 草稿
离开页面
  -> 保存当前草稿到 configs-{type}-autosave
```

### 6.3 训练配置与提交

```text
用户修改动态表单
  -> schema 校验/裁剪
  -> parseParams
  -> checkParams 生成 warnings/errors
  -> 右栏实时显示 TOML 参数预览
用户点击开始训练
  -> 按钮全局进入 loading
  -> schema -> parseParams
  -> Anima Fast 补丁可能拦截 fetch 并改写冲突字段
  -> POST /api/run
  -> 后端校验、保存 autosave TOML、创建异步 Task
  -> 返回 task_id 和日志 URL
  -> 前端提示成功/失败并恢复按钮
```

当前提交成功后主训练页只提示“训练已开始”，未自动绑定任务 store 或打开返回的日志 URL。新前端应保存 `task_id` 并提供明确的“查看日志/任务”入口，但首轮视觉上应保持克制。

### 6.4 配置导入、历史与预设

```text
导入 TOML/JSON
  -> 浏览器解析文件
  -> POST /api/config/validate-import
  -> reject: 显示错误
  -> redirect: 确认 -> sessionStorage 暂存 -> 跳转目标训练页 -> mounted 后应用
  -> ok: 按 schema 修正类型并覆盖当前表单

保存参数
  -> 将 {time,name?,value} 写入 localStorage configs-{type}
历史操作
  -> 应用 / 预览 / 重命名 / 删除
  -> 历史列表可导出 JSON，也可导入历史数组或单配置

加载预设
  -> GET /api/presets
  -> 按 metadata.train_type 过滤
  -> 经同一 validate-import 流程合并到当前参数
```

### 6.5 停止训练

```text
点击终止训练
  -> GET /api/tasks
  -> 过滤 RUNNING，取第一条
  -> 用户确认 task_id
  -> GET /api/tasks/terminate/{task_id}
  -> 显示结果
```

新前端应允许用户明确选择任务；但后端当前只允许一个并发训练，所以首轮可默认当前 active task，同时保留 task id 展示。

### 6.6 Anima Fast 安装与训练 gate

```text
进入页面
  -> GET /api/plugins/anima-lora/status
  -> 根据 feature_enabled/state/audit 禁用或启用训练
  -> 安装中且有 task_id 时重连日志 SSE + 进度 SSE
用户确认安装
  -> POST /api/plugins/anima-lora/install {dry_run:false}
  -> 打开日志 SSE
  -> 打开结构化进度 SSE
  -> 每 2 秒轮询 status
  -> ready 后刷新页面以恢复 schema/预览
训练前/提交时
  -> 根据 audit imports 禁用不可用选项
  -> 修正 compile/cache 等冲突组合
  -> POST /api/run；后端再次执行 ready/audit/preflight gate
```

### 6.7 Tagger

```text
进入页面
  -> schema 生成表单
  -> 原生补丁从 DOM 反向读取字段并创建底部 dock
  -> GET /api/tagger/status，每 1200ms
预下载
  -> POST /api/tagger/prefetch
  -> 300ms burst polling，最多约 36 秒
开始打标
  -> 从 DOM 拼装 TaggerInterrogateRequest
  -> POST /api/interrogate
  -> burst polling，展示下载/打标双进度
取消/重置
  -> POST /api/tagger/cancel 或 /reset
```

Vue 3 重写后应直接由响应式表单模型生成请求，删除“按中文 label 猜字段”和隐藏旧 Vue 按钮的逻辑。

### 6.8 数据集编辑器

```text
选择目录 -> GET /api/pick_file -> POST /api/dataset-editor/scan
  -> 保存 root/items/tags/categories
  -> POST /history
  -> 本地筛选并渲染分页图库
编辑 caption -> 标记 dirty -> POST /caption -> 刷新历史和筛选
批量选择/默认当前筛选结果
  -> 用户确认
  -> POST /batch
  -> 更新本地 items/tag counts -> POST /history
撤回/重做 -> POST /undo 或 /redo -> 合并变化 -> POST /history
```

## 7. 前端可执行操作与验证工作流

以下清单既是功能盘点，也是后续回归测试基线。

### 7.1 全局导航与显示

1. 打开首页并从侧栏进入所有训练、工具、帮助页面。
2. 展开/收起侧栏分组，识别当前页面。
3. 切换浅色/暗色并在刷新后保持设置。
4. 查看应用版本、关于、更新日志和指南。
5. 使用旧 `*.md`、`*.html` 和指定 alias 时仍到达正确页面。
6. 在桌面与窄屏下完成导航和核心操作。

### 7.2 训练配置

1. 进入每种训练类型，加载对应 schema、默认值和 GPU 选项。
2. 编辑文本、数值、选择、开关、数组和路径字段。
3. 查看实时参数预览、warnings 和 errors。
4. 全部重置。
5. 自动保存当前草稿，离开后返回并恢复。
6. 保存历史参数、应用、预览、重命名和删除。
7. 导出/导入历史 JSON。
8. 下载单份 TOML 配置。
9. 导入 TOML/JSON；验证同类型、拒绝和跨类型跳转三种结果。
10. 加载并应用与当前训练类型匹配的预设。
11. 提交训练，防止重复点击，显示后端结构化错误。
12. 获取当前任务、确认并终止训练。
13. 通过返回的 task id 查看训练日志和监控。

### 7.3 Anima Fast

1. 查看关闭、未安装、安装中、审计中、待审计、损坏、ready 状态。
2. 确认硬件/磁盘提示后启动安装。
3. 同时查看安装日志和结构化进度，断线后重连。
4. 刷新页面后恢复正在安装的任务。
5. ready 后启用训练；未 ready 时给出明确阻止原因。
6. 根据 audit 禁用 flash/Automagic 等不可用选项。
7. 阻止 compile、checkpoint、cache 的冲突组合。
8. 执行 repair、uninstall 和 dry-run/preflight（若产品决定暴露入口）。

### 7.4 Tagger

1. 选择图片目录和模型，配置阈值、附加/排除 tag 与输出规则。
2. 单独预下载模型并查看文件级与总下载进度。
3. 启动打标，下载完成后自动进入打标进度。
4. 忙碌期间中止任务。
5. 重置后端状态和表单。
6. 刷新页面后从 `/status` 恢复当前任务显示。
7. 验证重复任务会被后端拒绝并展示原因。

### 7.5 数据集编辑器

1. 手输或系统选择数据集目录并扫描。
2. 按分类、关键词、必须包含和排除 tag 筛选。
3. 浏览分页图库，切换每页数量和缩略图 contain/cover。
4. 选择当前页、筛选结果、全部或手工多选。
5. 编辑单张 caption；未保存切图时提示。
6. 使用常用 tag，维护本地快捷 tag。
7. 批量追加、删除、替换和排序。
8. 清理分隔符、空白、重复、转义和下划线。
9. 批量追加额外触发词。
10. 撤回/重做已保存操作，显示本次后端会话历史。
11. 使用键盘 `Ctrl+Z`、`Ctrl+Y`/`Ctrl+Shift+Z`。
12. 刷新或后端重启后正确处理非持久历史。

### 7.6 集成与工具

1. 在同源代理 iframe 打开 TensorBoard。
2. 使用设置中的自定义 TensorBoard URL，并持久化到本地。
3. 打开旧标签编辑器，验证 HTTP 与 WebSocket 代理。
4. 配置白名单脚本参数并提交 `/api/run_script`。
5. 后端不在 localhost:28000 时，工具调用仍使用当前 origin。

## 8. 已识别风险与待确认项

### 8.1 高风险

- **动态 schema 协议**：后端下发可执行代码，当前 UI 依赖 Koishi Schema API。它是训练表单重写的最大技术风险，应最先做兼容性 spike。
- **行为散落在补丁中**：Anima Fast、Tagger、数据集编辑、品牌和导航逻辑不只在 layout 内，漏迁任何补丁都会产生功能回退。
- **页面 URL 兼容**：后端、文档、用户书签和 schema 导入跳转依赖现有 `.html`/`sd3` 路径。
- **缺少前端测试基座**：现有测试无法证明交互等价，必须在替换前补契约和 E2E 基线。
- **SSE 生命周期**：安装/训练日志在导航、刷新、断线、结束时都必须正确关闭和重连，避免重复连接。

### 8.2 明确缺陷

- `/api/run_script` 当前硬编码 `127.0.0.1:28000`。
- Anima Fast 通过覆盖全局 `window.fetch` 修改训练请求。
- Tagger 通过中文 label 和 DOM class 反向读取表单值，UI 文案变化即可破坏请求。
- MutationObserver 被用于补建导航、状态和 dock，存在重复初始化及性能风险。
- schema 使用 `eval`，安全性、类型检查和可测试性差。
- 训练终止只选择第一个运行任务，错误字段还使用了 `messsage` 拼写。
- 当前下载 TOML 直接使用前端格式化结果，未走已存在的 `/api/config/normalize-for-export`。
- 两个数据集编辑入口存在重复/兼容层，需要在新 router 中收敛为同一组件。

### 8.3 实现前需要产品确认

- 是否继续暴露 Dreambooth、旧 SDXL alias 和当前未在主导航突出显示的页面。
- Anima Fast 的 repair、uninstall、dry-run、preflight 是否要成为可见 UI。
- `/task.html` 的目标功能是简单任务列表，还是需要整合训练日志与监控。
- 文档型页面内容是否原样迁移，还是只保持入口并链接项目文档。
- 是否保留旧外部 tageditor；若保留，Vue 3 只提供 iframe shell，不重写其内部应用。

## 9. 重写工作计划

### 阶段 0：冻结基线与契约

目标：在删除旧 UI 前得到可验证的等价标准。

- 为本文 API 建立 TypeScript 类型和请求/响应 fixture。
- 从 FastAPI OpenAPI 与现有 Pydantic 模型核对实际字段。
- 为所有旧 URL 建立路由兼容矩阵。
- 录制关键页面桌面/移动截图和用户流程。
- 建立 Playwright smoke 测试：启动、导航、schema 加载、训练提交 mock、Tagger、数据集编辑、iframe。
- 明确 `frontend/dist` 切换和回滚方式。

退出条件：API、路由和工作流基线均有自动化或明确手工用例。

### 阶段 1：Vue 3 工程骨架

- 创建 Vite + Vue 3 + TypeScript 工程和可重复构建命令。
- 配置 Vue Router、Element Plus、基础 i18n、ESLint/类型检查/测试。
- 实现 AppShell、侧栏、主题、响应式布局和错误边界。
- 保持输出目录与 `MIKAZUKI_FRONTEND_DIST` 托管兼容。
- 在开发服务器配置 `/api`、`/proxy` 同源代理。

退出条件：生产构建可由 FastAPI 托管，首页和全部兼容路由不 404。

### 阶段 2：API 与基础设施层

- 实现统一 `apiClient` 和领域 API 模块。
- 定义 `APIResponse`、任务、插件、Tagger、数据集类型。
- 实现可取消 polling、SSE 自动重连、storage 版本迁移和 dirty guard。
- 所有请求使用相对 URL，不写死 host/port。
- 对 API client 和 composable 写单元测试。

退出条件：可在 mock API 下验证成功、fail、pending、HTTP error、断线和取消。

### 阶段 3：schema 兼容与动态表单

- 做 Koishi Schema 兼容 spike，列出实际用到的 schema 类型、role、默认值、description 和校验规则。
- 首选将后端 schema 在受控适配层转换为内部声明式 `FormSchema`，隔离 `eval`。
- 实现动态控件、分组、路径选择、数组/KV 参数和 GPU 选择。
- 实现参数解析、warnings/errors、预览和 `/normalize-for-export`。
- 为全部 `mikazuki/schema/*.ts` 做渲染快照与关键字段测试。

退出条件：所有训练类型字段数量、默认值、提交 payload 与旧 UI 基线一致。

### 阶段 4：训练主流程

- 实现训练三栏页面并复刻现有视觉层级。
- 迁移草稿、历史、预设、导入/导出和跨页导入。
- 实现提交防重、结构化错误、task id、日志/监控入口和终止。
- 保留 `configs-{type}`、`configs-{type}-autosave` 等 storage key，或提供一次性迁移。
- 覆盖 basic/master/flux/sd3/anima-finetune/dreambooth。

退出条件：第 7.2 节全流程通过，现有用户本地配置不会无故丢失。

### 阶段 5：Anima Fast

- 将安装状态机、日志 SSE、进度 SSE 和重连改为显式 store/composable。
- 将依赖审计和参数冲突规则做成字段级校验，删除全局 fetch patch。
- 实现安装、训练 gate 和产品确认后的管理入口。
- 覆盖刷新恢复、安装完成、失败、断线、环境漂移。

退出条件：第 7.3 节通过，后端 gate 失败信息完整可见。

### 阶段 6：Tagger 与数据集编辑器

- Tagger 改为受控表单模型，保留双进度、预下载、取消和重置。
- 数据集编辑器组件化图库、筛选、选择、caption、批量编辑和会话历史。
- 保留快捷 tag、分页大小和缩略图模式 storage key。
- 将 `/native-tageditor.html` 与 `/dataset-editor.html` 指向同一 Vue 页面。

退出条件：第 7.4、7.5 节通过，后端 API 测试和前端 E2E 同时通过。

### 阶段 7：集成页与静态内容

- 实现 TensorBoard 与旧 tageditor iframe shell。
- 实现工具页、设置页、任务页、版本/更新、关于、日志和指南。
- 验证代理错误、外部服务未启动和 WebSocket 行为。

退出条件：全部旧导航目标有可用的新页面或明确保留的后端页面。

### 阶段 8：切换、清理与发布

- 生成新 `frontend/dist` 并切换默认托管。
- 在一个过渡版本保留旧 dist 的可回滚构建产物或发布 tag，不在运行时代码中维护双实现。
- 删除旧 VuePress hash bundle patch 脚本、恢复 bundle 和失效静态字符串测试。
- 更新开发、构建、发布和前端定制文档。
- 运行 Python 测试、前端单元/组件/E2E、生产构建和 Windows 整合包 smoke test。

退出条件：无运行时 console error，无已知关键工作流回退，可从干净 clone 复现构建。

## 10. 建议测试矩阵

| 层级 | 工具 | 覆盖重点 |
|---|---|---|
| 类型/静态检查 | `vue-tsc`、ESLint | API、props、schema 适配 |
| 单元测试 | Vitest | API client、storage、解析、冲突规则、polling/SSE |
| 组件测试 | Vue Test Utils | 动态表单、状态按钮、数据集编辑交互 |
| API 契约 | 现有 pytest + OpenAPI fixture | 请求字段、响应包装、错误状态 |
| E2E | Playwright | 第 7 节核心工作流与路由兼容 |
| 视觉回归 | Playwright screenshot | 训练三栏、Tagger、数据集编辑、暗色和窄屏 |
| 发布 smoke | FastAPI 托管生产 dist | 静态资源、刷新深链、代理、SSE、Windows 路径 |

## 11. 非目标

- 本阶段不创建 Vue 工程、不改现有 UI、不修改后端 API。
- 首轮重写不重构训练算法、任务管理器、Tagger 引擎或数据集文件格式。
- 不重写 TensorBoard 和旧外部 tageditor 的内部实现。
- 不在首轮顺带更名 `/lora/sd3.html`、`sd3-lora` 等兼容 key。
- 不通过长期保留两套前端运行时代码来实现兼容；兼容应落在 URL、storage 迁移和 API 契约层。

## 12. 开工顺序建议

真正进入实现阶段时，优先顺序应为：

1. API/路由契约基线。
2. schema 兼容 spike。
3. Vue 工程骨架和动态训练页最小纵切。
4. 完成训练主流程。
5. Anima Fast。
6. Tagger 与数据集编辑器。
7. 集成/文档页、视觉回归、切换清理。

最先做 schema spike，而不是先画完整页面。若 schema 无法稳定转换，后续所有训练表单工作都会返工。
