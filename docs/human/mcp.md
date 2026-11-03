# 连接 MCP，让 agent 使用项目

MCP server 将当前后端的训练、队列、图片/Caption 阅读、日志、指标与调参功能提供给其他 agent。启动 GUI 时默认同时启用内置 MCP，网页和 agent 使用同一个后端与任务历史。完整操作流程见 [Agent MCP 使用指南](../agent/usage/mcp.md)。

## 准备

先按[安装说明](../../README-zh.md)准备并启动后端。已有后端时继续使用，不要为每个 agent 新开一份服务：

```powershell
.\venv\Scripts\python.exe gui.py
```

Linux 对应 `venv/bin/python gui.py`。默认地址是 `http://127.0.0.1:28000`；浏览器打开 `/api/v2/health` 应能看到健康状态和版本。MCP 依赖已包含在正常安装流程和 Windows 便携包中，无需另启 MCP 进程。

## 连接内置 HTTP MCP

在支持 **Streamable HTTP** 的 MCP 客户端中添加服务器，填写：

```text
名称：lora-scripts
传输：Streamable HTTP
URL：http://127.0.0.1:28000/mcp/
```

MCP 与 GUI 使用同一端口。修改了 GUI 端口或启动时自动换端口后，应复制 GUI 设置中显示的实际 MCP 地址；保留末尾的 `/mcp/`。这是 MCP 协议地址，普通浏览器打开它不等于已完成连接。客户端连接后可以列出训练、数据与监控工具，不需要填写 Python 命令。

### 即时开关

在 GUI 的“设置 → 后端服务 → MCP 服务”中，可立即开启或关闭内置 HTTP 服务，无需重启后端。首次启动默认开启；开关状态自动保存到 `config/app-settings.json`，下次启动沿用。关闭后不再接受新的 HTTP MCP 请求，已经创建的训练或 Caption 任务继续运行。

无前端时也可使用设置 API：

```powershell
Invoke-RestMethod http://127.0.0.1:28000/api/v2/settings/mcp
Invoke-RestMethod http://127.0.0.1:28000/api/v2/settings/mcp -Method Patch -ContentType 'application/json' -Body '{"enabled":false}'
```

将 `false` 改为 `true` 即可开启。查询响应包含 `enabled`、`running` 和 `endpoint`，分别表示保存的开关、当前运行状态和连接地址；`error` 提供启动或设置加载失败的原因。开关只控制内置 HTTP MCP；下面的独立 stdio 适配器由客户端启动，不受该开关控制。

内置 HTTP MCP 仅接受本机回环访问，并校验 Host/Origin。客户端应运行在后端所在机器，使用 GUI 显示的本机地址；即使 GUI 使用 `--listen`，也不要把此地址作为无需鉴权的远程服务发布。

### 仅启动 API，无需前端

只供 agent 使用时，在已安装完整后端依赖的环境中，可改用以下单进程入口，无需构建网页。与上面的 GUI 启动二选一，已有后端时不再执行：

```powershell
$env:MIKAZUKI_DEV = '1'
.\venv\Scripts\python.exe -m uvicorn mikazuki.app.application:app --host 127.0.0.1 --port 28000 --workers 1
```

Linux：

```sh
MIKAZUKI_DEV=1 venv/bin/python -m uvicorn mikazuki.app.application:app --host 127.0.0.1 --port 28000 --workers 1
```

在仓库根运行；这里的 `MIKAZUKI_DEV=1` 用于避免自动打开浏览器，该命令未启用热重载。直接 Uvicorn 入口不运行 GUI 的依赖准备步骤，因此须事先完成项目安装。此入口同样在应用启动时加载 MCP 开关，默认提供 `/mcp/`；网页根路径可能提示前端未构建，不影响 API/MCP。

## 可选：独立 stdio 适配器

客户端只支持 stdio，或需要使用独立 Python 环境时，可保留独立入口。完整项目环境已包含依赖；只有独立 Python 3.10+ 环境需要安装轻量依赖：

```powershell
.\venv\Scripts\python.exe -m pip install -r requirements/mcp.txt
```

独立适配器自身不需要 PyTorch/CUDA，但连接的后端仍须使用完整项目环境。`requirements/mcp.txt` 不能代替后端的 `requirements.txt`。

### 配置 stdio 客户端

让客户端启动以下进程，路径换成自己的绝对路径：

```text
command: C:/path/to/lora-scripts/venv/Scripts/python.exe
args:
  - C:/path/to/lora-scripts/mcp_server.py
  - --base-url
  - http://127.0.0.1:28000
```

Linux 的 command 可设为 `/path/to/lora-scripts/venv/bin/python`，入口为 `/path/to/lora-scripts/mcp_server.py`。使用绝对路径入口不要求客户端设置工作目录；若已将 cwd 设为仓库根，也可以使用 `python -m mikazuki.mcp`。

支持 `mcpServers` JSON 配置的客户端可使用：

```json
{
  "mcpServers": {
    "lora-scripts": {
      "command": "C:/path/to/lora-scripts/venv/Scripts/python.exe",
      "args": [
        "C:/path/to/lora-scripts/mcp_server.py",
        "--base-url", "http://127.0.0.1:28000"
      ]
    }
  }
}
```

客户端若使用其他配置格式，填写相同的 command/args 即可。地址也可通过环境变量 `MIKAZUKI_BASE_URL` 提供；命令行参数优先。`--timeout` 默认 30 秒，可设为大于 0、不超过 600 的秒数。

`--base-url` 是适配器连接后端的 HTTP origin，只填写协议、主机和端口，不附加 `/api/v2` 或 `/mcp/`。stdio 进程使用后端业务 API，内置 HTTP MCP 关闭时仍可工作；它不会启动另一个后端或训练队列。

## 验证与使用

客户端启动后应能列出 `get_workspace_status`、`list_trainers`、`compile_training` 等工具。先调用 health、列举训练器和数据目录验证连接，无需启动真实训练。命令行直接运行时等待 stdin 是 stdio server 的正常行为。

可以给 agent 这样的任务：

> 阅读项目的 agent 使用文档，检查指定数据集的图片和 Caption，根据目标配置一轮训练；跟踪日志、指标与固定提示词样图，保留本轮配置，再提出或执行授权范围内的下一轮调整。

原生图片工具可让支持图片的 MCP 客户端看到数据和样图。训练输出建议放在 `output/<实验名>/`，这样 agent 可以直接检查产物。

| 问题 | 处理 |
| --- | --- |
| HTTP MCP 无法连接 | 确认后端已运行、GUI 中 MCP 已开启，使用实际端口和 `/mcp/` 地址；客户端须在同一机器 |
| HTTP MCP 返回 503 | 服务已关闭或尚未就绪，查看 GUI 设置中的状态与错误 |
| 浏览器打开 `/mcp/` 返回 405 | 此地址接收 MCP POST 协议请求，使用 Streamable HTTP 客户端连接；普通 GET 不用于验证 |
| GUI 显示开启但服务未运行 | 查看设置中的状态与启动日志；旧环境更新依赖后重启后端 |
| stdio 没有 MCP 工具 | 确认 command 和入口为绝对路径，MCP 依赖装在该解释器中 |
| stdio 工具已出现但无法连接 | 检查后端是否运行、base-url/端口是否一致；适配器不会自动启动后端 |
| 后端报告 schema 或 artifacts 接口缺失 | 更新后端与 MCP 到同一份源码，完成依赖更新后重启 |
| 调用超时 | 查看队列或变更历史确认是否已执行，避免直接重复提交；必要时调整 timeout |
| 数据 ID 失效 | 后端重启后重新扫描数据 |

后端按本地单用户工作台设计，默认仅监听回环地址。多个 MCP 客户端可连接同一个服务；同一工作区不要运行多个 Uvicorn worker。启动 GUI 会提供 MCP 服务，但不会自动配置或连接外部客户端。
