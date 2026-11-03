# 前端版本与自动下载

仓库根目录的 `version.json` 是应用与前端制品的唯一版本源。Vite 构建会自动在
`frontend/dist/build-info.json` 写入应用版本、前端版本、Git commit 和构建时间；自动安装后还会
记录实际下载源和安装时间。
启动器只接受与 `version.json` 精确匹配的前端，避免 `git pull` 后出现前后端错配。

`GET /api/v2/health` 会返回应用版本、发布通道、tag，以及前端要求版本、已安装版本、
构建 commit、构建时间和下载源；设置页也会显示已安装前端版本与来源。

## 发布流程

创建并推送 `v*` tag（例如 `v2.1.0`）、发布 Release，或手动指定已有 Git tag，
都会触发 `release-frontend.yml`。工作流运行前端测试、类型检查与构建，并将以下文件上传到实际指定的 tag：

- `frontend-dist.zip`
- `frontend-dist.zip.sha256`

发布 tag 无需与 `version.json` 的 `tag` 或版本一致，也不要求同步 `frontend/package.json` 的版本或启用自动下载。
Release 不存在时会自动创建：`vX.Y.Z`（可带 `+build` 后缀）作为正式版，其他 tag 作为预发布版；已有 Release 保留原设置并覆盖同名附件。

应用版本和前端构建信息仍取自 `version.json`，CI 不会改写这些元数据。
如需让源码检出后自动下载前端，应在打 tag 前将该文件的 `tag` 设为实际发布 tag，并启用 `frontend.autoDownload`；
应用版本、前端版本和 `channel` 按实际发布内容更新。未启用自动下载时，源码运行仍需手动构建前端。

前端仅构建一次，结果通过 Actions artifact 同时用于 GitHub Release、Jihulab 镜像和 Windows 包。
GitHub 前端附件发布成功后，会自动调用 Windows NVIDIA 便携版构建，将前端、后端和 Python/CUDA 依赖一起打包为
`lora-scripts_windows_portable_nvidia.7z` 并上传到同一 Release。
Release 事件及手动补包方式见 [Windows 便携版发布说明](windows-portable.md)。
镜像上传与 Windows 打包独立执行，失败时可单独重试，前端 artifact 保留 7 天。

本地也可以执行：

```powershell
cd frontend
pnpm install --frozen-lockfile
pnpm run build
cd ..
python -m mikazuki.scripts.package_frontend_release --output release
```

## 下载源

默认下载源是同仓库的 GitHub Release。下载源配置优先级为：启动参数、环境变量、
`config/frontend-download.json`、内置默认值。

### GitHub Release

```powershell
python gui.py --frontend-source github
```

可配置项：

- `MIKAZUKI_FRONTEND_GITHUB_REPOSITORY`，默认 `Akegarasu/lora-scripts`
- `MIKAZUKI_FRONTEND_GITHUB_BASE_URL`，默认 `https://github.com`

### Jihulab Generic Package

```powershell
python gui.py --frontend-source cn
```

`cn` 是 `jihulab` 的别名。制品地址遵循：

Linux 的 `scripts/run_gui_cn.sh` 已默认传入该下载源；显式传入其他
`--frontend-source` 仍可覆盖它。

```text
https://jihulab.com/api/v4/projects/<project>/packages/generic/<package>/<version>/<file>
```

可配置项：

- `MIKAZUKI_FRONTEND_JIHULAB_PROJECT`，项目数字 ID 或 `namespace/project`
- `MIKAZUKI_FRONTEND_JIHULAB_PACKAGE`，默认 `lora-scripts-frontend`
- `MIKAZUKI_FRONTEND_JIHULAB_BASE_URL`，默认 `https://jihulab.com`

GitHub Actions 中配置 `JIHULAB_PROJECT_ID` 仓库变量和 `JIHULAB_TOKEN` secret 后，会把
同一份制品同步上传到 Jihulab 软件包库。

### 静态服务器 / Cloudflare Pages

```powershell
python gui.py --frontend-source static \
  --frontend-static-base-url https://downloads.example.com/frontend
```

静态目录约定为：

```text
<base-url>/<frontend-version>/frontend-dist.zip
<base-url>/<frontend-version>/frontend-dist.zip.sha256
```

因此把发布目录同步到 Cloudflare Pages、S3 或任意静态服务器即可，不需要修改下载器。

### 自动回退

```powershell
python gui.py --frontend-source auto
```

默认依次尝试 GitHub、Jihulab，以及已配置的静态源。可通过
`MIKAZUKI_FRONTEND_AUTO_ORDER=jihulab,github,static` 调整顺序。

持久化配置示例：

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

将其保存为 `config/frontend-download.json`。该文件已被 Git 忽略，不会在 `git pull` 时产生冲突。

## 安全与失败处理

- 压缩包必须通过 SHA-256 校验。
- 拒绝 ZIP 中的绝对路径和 `..` 路径，避免解压到目标目录之外。
- 在临时目录完成下载、校验和解压后才原子替换 `frontend/dist`。
- 安装失败时保留原前端；稳定版本无法获得匹配前端时终止启动并显示可操作错误。
- `--skip-frontend-download` 可用于离线排障，`--force-frontend-download` 可强制重装。
