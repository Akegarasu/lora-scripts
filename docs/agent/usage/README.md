# Agent 使用指南

目标：调用已有能力完成训练和数据处理。通常无需修改源码，也无需读取开发文档。

1. 确认后端可用：`GET http://127.0.0.1:28000/api/v2/health`。GUI 默认提供同端口 `/mcp/` 的 Streamable HTTP MCP；已有后端时直接复用，不要再启动一个队列进程。
2. 读取训练器目录、所选训练器参数和 GPU；浏览实际模型与数据路径。不要从文档猜测本机已有权重。
3. 按[数据指南](datasets.md)检查图片、Caption、扫描是否截断；需要补 Caption 时先完成数据处理。
4. 按[训练指南](training.md)构造草稿，以 `persist=false` 预览编译，处理 `errors` 和相关 `warnings`。
5. 提交一次任务，保存返回的 `job.id`，用该 ID 查状态、日志、指标和产物。任务创建超时先查队列，避免重复提交。

MCP 接入与工具调用见 [MCP 使用](mcp.md)。不能使用 MCP 时，可按本文列出的 HTTP API 操作。交互式接口文档位于运行中后端的 `/docs`，API schema 位于 `/openapi.json`；训练草稿的完整 JSON Schema（包含 simple 数据集字段）由 `/api/v2/training/schema` 提供。

## 启动与运行边界

依赖和前端已安装时，在仓库根目录运行 `python gui.py`；Windows 通常用 `venv/Scripts/python.exe`，Linux 用 `venv/bin/python`。首次安装按[人类安装文档](../../../README-zh.md)。`--skip-prepare-environment` 仅适用于已准备好的环境。

只需要 MCP/API 时可用[单进程 Uvicorn 入口](../../human/mcp.md#仅启动-api无需前端)，省去前端构建；仍须先安装完整后端依赖。

内置 HTTP MCP 的开关在 GUI 设置中，也可 `GET /api/v2/settings/mcp` 查询，`PATCH /api/v2/settings/mcp` 提交 `{"enabled":true}` 或 `{"enabled":false}` 即时切换。首次默认开启，选择持久化到 `config/app-settings.json`；不应为了连接失败就改用户保存的开关。独立 stdio 入口继续可用，且不受此开关影响。

所有路径由后端所在机器解释。相对训练路径基于仓库根目录；文件浏览路径基于指定 root。不要把客户端电脑路径发给另一台机器的后端。

后端是本地工作台，没有多用户鉴权。默认保留 `127.0.0.1` 监听；内置 HTTP MCP 只接受回环客户端并校验 Host/Origin，使用设置页显示的本机地址。共享 GPU 槽位只在同一后端进程内生效。直接执行 `scripts/train.*` 会绕过队列，不能与队列任务混用来保证互斥。

## 常见故障

| 现象 | 下一步 |
| --- | --- |
| 无法连接 | 检查已有后端、地址和端口；不要先启动第二个实例 |
| `/` 返回 `frontend_not_built`，health 正常 | API 仍可用；网页需要按安装指南构建前端 |
| 编译响应 HTTP 200 | 仍须检查 `errors`；200 不代表配置有效 |
| 一直 queued | 同时检查训练和 Caption 任务；两者共享一个执行槽 |
| 重启后 failed / interrupted | 查看历史日志；队列不会自动恢复，修正后新建任务 |
| Caption dataset ID 失效 | 重新 inspect，再使用返回的新 ID |
| 模型目录为空 | 模型由用户另行提供；确认底模类型和路径后再配置 |
| 没有指标 | 检查任务状态、事件文件与 `log_with`；空曲线不等于任务失败 |

向用户报告任务 ID、状态、使用的数据与模型、输出目录和实际验证范围。退出码成功不代表训练质量已评估。
