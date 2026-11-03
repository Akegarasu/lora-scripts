# Agent 开发指南

只使用项目时读[使用文档](../usage/README.md)。本文件描述当前实现，不维护待实现的大型设计计划。

## 代码地图

| 位置 | 职责 |
| --- | --- |
| `gui.py`、`mikazuki/launch_utils.py` | 环境准备、前端校验、启动 Uvicorn |
| `mikazuki/app/` | FastAPI `/api/v2`、Caption、Tag Editor 路由及 SSE |
| `mikazuki/catalog/` | 从 sd-scripts argparse 提取 manifest，以 YAML overlay 增强显示与默认值 |
| `mikazuki/compiler/` | `TrainDraft` 校验、模型/数据路径、TOML、采样文本、Accelerate 命令 |
| `mikazuki/jobs/` | 训练状态持久化、子进程、共享执行槽、日志与 TensorBoard 指标 |
| `mikazuki/captioning/` | 数据扫描、模型目录、独立生成 worker、结果复核与 sidecar 写入 |
| `mikazuki/tag_editor/` | 带 revision 的预览、批量编辑、冲突检测和回滚 |
| `mikazuki/storage/` | 工作区路径边界、文件枚举、输出读取 |
| `mikazuki/mcp/`、`mcp_server.py` | 共用工具定义、GUI 内置 Streamable HTTP MCP、独立 stdio 入口 |
| `frontend/src/` | Vue 3 + Pinia + Element Plus 工作台；API 类型/客户端与各功能视图 |
| `scripts/dev/` | 随仓库分发的 sd-scripts 快照；来源与差异说明在 `UPSTREAM.md` |
| `mikazuki/tests/`、`frontend/tests/` | 后端 unittest 与前端 Node tests |

## 关键边界

训练流程：`TrainDraft → catalog 校验 → compile_draft → run artifacts → JobRunner → accelerate → scripts/dev`。前端和 MCP 都提交草稿，不能自行拼接 shell 命令或维护另一套默认参数。命令为 argv 数组，通过 `subprocess.Popen` 执行。

同一工作区只能有一个后端队列进程。`DeviceLease` 是进程内信号量，训练与 Caption 默认共享容量 1；多 worker 或额外实例会绕过互斥。等待顺序没有 FIFO 保证。持久化保存历史，不等于持久化调度：启动时训练未终态转 failed，Caption 活动任务转 interrupted；不能把读取数据库当作无副作用的任意外部进程操作。

MCP 工具通过业务 API 复用队列，不能初始化第二份 `JobStore`/`JobRunner`，也不能在工具调用中启动第二套服务。内置 HTTP 服务在同一 FastAPI 应用内用 `httpx.ASGITransport` 调用 `/api/v2`；独立 stdio 使用普通 HTTP 客户端。工具应保留业务校验错误，列举和日志限制返回量；不要自动重试可能已执行的写请求。完整连接与调用流程见[使用文档](../usage/mcp.md)。

`mikazuki/mcp/integration.py` 中的 `MCPService` 管理内置 `/mcp/` 的生命周期、开关与状态。应用 lifespan 启动 SDK session manager，使用 stateless Streamable HTTP 与 JSON 响应；同一生命周期内保持单个服务。GUI 与 headless Uvicorn 共用此启动流程。`GET/PATCH /api/v2/settings/mcp` 查询/更新 `enabled`，设置持久化到 `config/app-settings.json`；首次默认开启，切换即时生效且不取消已经创建的业务任务。该开关不控制独立 stdio 进程。

内置路由只接受回环客户端，并使用 SDK 的 Host/Origin 校验。不要因为 GUI 支持 `--listen` 就移除 MCP 的边界；MCP 路由必须在 SPA fallback 前注册。`endpoint` 应反映实际请求端口，不能硬编码默认 28000。

适配器使用官方 [MCP Python SDK v1](https://py.sdk.modelcontextprotocol.io/v1/)，版本范围为 `mcp>=1.28,<2`，不要无意升级到不同主版本。SDK 已纳入根 `requirements.txt` 与正常打包流程；`requirements/mcp.txt` 保留给独立轻量 stdio 环境。训练结构通过 `/api/v2/training/schema` 提供标准 JSON Schema 与 simple 数据集定义；其他请求 schema 从当前 OpenAPI 提取，工具层不要再维护一份漂移的字段清单。

文件与写入边界由服务层实施，不能只靠前端隐藏。保留路径解析、后缀限制、revision/内容冲突检查、备份与原子替换。新增调用入口也必须走这些服务。

## 参数与上游维护

训练脚本的 argparse 定义是参数事实源；`catalog/generated/sd_scripts_manifest.json` 是生成物，`catalog/overlays/*.yaml` 维护中文帮助、分组、优先级、工作台默认值。`required/recommended/advanced/dangerous/hidden` 是展示分类；新增说明或调整层级时不要顺便改变 `effectiveDefault`。

同步 `scripts/dev` 前先读 [UPSTREAM.md](../../../scripts/dev/UPSTREAM.md) 和机器可读 `UPSTREAM.json`，比较本地适配；保留许可证与上游说明。同步后生成并检查 manifest：

```sh
python -m mikazuki.catalog.inspector generate --scripts-root scripts/dev
python -m unittest discover -s mikazuki/tests/catalog -t .
python -m unittest discover -s mikazuki/tests/compiler -t .
```

编译器处理必填、类型/choices、受管理字段、路径、缓存/增强冲突及模型约束；不要只加前端校验。确认编译结果可被真实训练 parser 读取：

```sh
python -m mikazuki.catalog.validate_config --trainer sdxl.lora --config config/runs/<run-id>/train.toml
```

生成/读取 parser 依赖完整训练环境。通过 parser 或微型 CPU 测试只证明配置/局部算子可运行，不等于完整 GPU 训练已验证。

## 开发与验证

依赖以根 `requirements.txt` 为准；GPU 组合在 `requirements/pytorch-*.txt` 和 `requirements/onnxruntime-*.txt`，不要同时装两套 CUDA 配置。根依赖已经迁到 Pydantic 2；旧虚拟环境可能需重建。`requirements/mcp.txt` 只供独立适配器，不替代训练环境。

使用已完成项目安装的 Python，在仓库根执行相关测试或完整后端测试：

```sh
python -m unittest discover -s mikazuki/tests -t .
```

前端使用 `frontend/package.json` 固定的 pnpm，Node 版本遵循该文件 engines：

```sh
cd frontend
corepack pnpm install --frozen-lockfile
corepack pnpm test
corepack pnpm run build
```

`build` 包含 TypeScript 检查。后端可用 `python gui.py --dev`；前端独立开发用 `corepack pnpm dev`。不要对用户正在训练的进程启用热重载。修改数据写入、任务取消和路径逻辑时覆盖相应失败/并发边界；纯文档变更检查链接即可。

修改 MCP 集成时覆盖 HTTP 初始化/工具发现、启用/关闭即时切换与重启持久化、回环/Host/Origin 限制，以及应用 shutdown 的资源释放。业务 API 与独立 stdio 在内置服务关闭后仍应可用；测试使用临时 settings 路径和模拟任务，不能改工作区真实设置或启动 GPU 训练。

## 前端维护

当前工作台位于 `frontend`；`frontend-old` 不作为新功能入口。API 访问集中在 `src/api/client.ts`，类型在 `src/api/types.ts`；状态放到对应 Pinia store，页面放到 `src/features/`。

样式延续 `src/styles.css` 的浅色/深色语义变量：中性色主体、状态色只表达状态、紧凑表单、适量留白、有限层级。使用已有 Element Plus 图标和组件，避免为普通内容叠加卡片、渐变或阴影。空态、错误态、队列状态、窄屏及深色都需可读；参数帮助和校验内容不能为了简化界面而隐藏。

版本、前端分发、便携包与重跑流程见[发布指南](releases.md)。不要将本机模型、数据、缓存、密钥、`config/runs`、日志或输出纳入发布归档。
