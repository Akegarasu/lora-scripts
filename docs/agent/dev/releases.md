# 版本、前端分发与 Windows 发布

版本事实源为根 `version.json`。Vite 生成 `frontend/dist/build-info.json`，记录应用/前端版本、commit、构建时间；下载器另记录来源与安装时间。`GET /api/v2/health` 返回相关版本信息。发布 tag 与应用版本是独立字段，工作流不会自动改写版本文件。

## 一次构建，共用制品

`.github/workflows/release-frontend.yml` 的 **Release frontend and Windows portable** 支持：

- 推送 `v*` tag：构建该 tag 的源码。
- 发布 Release：构建对应 tag 的源码。
- 手动 Run workflow：构建所选分支在触发时的提交；输入 `tag` 仅指定上传目标，必须已有该 Git tag。不存在的 Release 会创建，已有附件会覆盖，不移动 Git tag。

前端依次锁定安装、测试、类型检查与构建，生成 `frontend-dist.zip` 和 `.sha256`，保存同一份 Actions artifact，上传 GitHub 后供 Windows 两个 CUDA 配置和 Jihulab 镜像共用。各制品使用相同源码 commit；同目标 tag 发布串行执行。版本信息仍来自该提交的 `version.json`，不能仅凭 Release 标题推断实际源码版本。

更新已有 Release：从包含修复的分支手动执行并填写原 tag。重试旧运行不会载入新工作流或新源码。artifact 保留 7 天，期间可 Re-run failed jobs；过期后重新运行完整工作流。镜像和 Windows 任务独立，单项失败不取消其他配置。

本地前端打包：

```sh
cd frontend
corepack pnpm install --frozen-lockfile
corepack pnpm test
corepack pnpm run build
cd ..
python -m mikazuki.scripts.package_frontend_release --output release
```

## 自动下载

源码开发版本通常需手动构建前端；是否自动下载由 `version.json` 的 `frontend.autoDownload` 控制。要发布可自动下载的版本，构建前将其中 `tag` 设为实际制品目标 tag，并启用 autoDownload。下载器只接受精确匹配的版本。

配置优先级：启动参数 → 环境变量 → `config/frontend-download.json` → 默认。支持 `github`、`jihulab`（别名 `cn`）、`static`、`auto`、`off`。

| 配置 | 用途 |
| --- | --- |
| `MIKAZUKI_FRONTEND_GITHUB_REPOSITORY` | 默认 `Akegarasu/lora-scripts` |
| `MIKAZUKI_FRONTEND_GITHUB_BASE_URL` | 默认 `https://github.com` |
| `MIKAZUKI_FRONTEND_JIHULAB_PROJECT` | 数字项目 ID 或 `namespace/project` |
| `MIKAZUKI_FRONTEND_JIHULAB_PACKAGE` | 默认 `lora-scripts-frontend` |
| `MIKAZUKI_FRONTEND_JIHULAB_BASE_URL` | 默认 `https://jihulab.com` |
| `MIKAZUKI_FRONTEND_AUTO_ORDER` | 如 `jihulab,github,static` |

`config/frontend-download.json` 示例（被 Git 忽略）：

```json
{
  "source": "jihulab",
  "githubRepository": "Akegarasu/lora-scripts",
  "jihulabProject": "Akegarasu/lora-scripts",
  "jihulabPackage": "lora-scripts-frontend",
  "staticBaseUrl": "https://downloads.example.com/frontend",
  "autoOrder": ["jihulab", "github", "static"]
}
```

静态源目录是 `<base-url>/<frontend-version>/frontend-dist.zip` 和同名 `.sha256`。使用 `python gui.py --frontend-source static --frontend-static-base-url <url>`。Jihulab CI 镜像使用仓库变量 `JIHULAB_PROJECT_ID` 和 secret `JIHULAB_TOKEN`。

下载器校验 SHA-256，拒绝 ZIP 绝对路径/越界路径，在临时目录完成验证后原子替换；失败保留原前端。`--skip-frontend-download` 用于离线排障，`--force-frontend-download` 强制重装。

## Windows 便携包

入口为 `.github/workflows/release-windows-portable.yml`，由主发布流程调用；实现位于 `.github/scripts/build-windows-portable.ps1`。依赖版本以以下源文件为准，避免在多份文档重复维护：

- 通用应用/训练依赖（含内置 MCP SDK）：根 `requirements.txt`。
- PyTorch、torchvision、xFormers：`requirements/pytorch-cu130.txt`、`requirements/pytorch-cu128.txt`。
- ONNX Runtime：对应 `requirements/onnxruntime-*.txt`。
- 构建工具：`requirements/tooling.txt`；嵌入式运行时与打包参数在脚本中。

输出 `lora-scripts_windows_portable_nvidia.7z`（cu130）、`lora-scripts_windows_portable_nvidia_cu128.7z`，附各自 SHA-256。安装对应 CUDA 官方索引的 GPU wheels，然后安装通用依赖；不能混用不同索引的 xFormers wheel。

从确定的源码提交导出应用，包含 `scripts/dev`；不复制本机 venv、模型、数据、缓存或 Git 凭据。在完整 Python 构建 wheels，再安装到嵌入式 Python，保留必要 DLL。启动器定位到包内工作区和缓存，`PYTHONHOME` 固定到内置 Python。

发布前检查依赖一致性、CUDA 版本、训练入口、GUI health、静态资源、内置 `/mcp/` 的工具发现与设置开关，以及 7z 完整性与单附件 2 GiB 限制。发布包不带本机 `config/app-settings.json`，首次启动使用默认 MCP 开关。GitHub 托管 runner 的检查不包含真实 NVIDIA GPU 训练；报告验证结果时区分依赖/CPU检查与实际模型训练。`runtime-info.json`、`installed-packages.txt` 记录最终运行时信息。

人类安装选择见[操作指南](../../human/README.md)。
