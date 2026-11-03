# Windows NVIDIA 便携版发布

便携包参考 [ComfyUI 的 Windows 打包流程](https://github.com/Comfy-Org/ComfyUI/blob/master/.github/workflows/windows_release_package.yml)，
使用 Windows runner 构建依赖 wheel、嵌入式 Python 和 7-Zip，输出：

- `lora-scripts_windows_portable_nvidia.7z`
- `lora-scripts_windows_portable_nvidia.7z.sha256`

## 触发方式

三个入口统一由 `release-frontend.yml`（**Release frontend and Windows portable**）负责：

1. **发布 Release**：发布正式版或预发布版时，自动构建该 Release 的 tag 并上传附件。
2. **手动补包或重跑**：在 Actions 中选择 **Release frontend and Windows portable** → **Run workflow**，
   填写已有 Git `tag`。构建源码取自这个 tag；不会用所选工作流分支的 HEAD 替代，也不会创建或移动 tag。Release 不存在时会自动创建。
3. **推送 `v*` tag**：发布前端和 Release 后，通过 `workflow_call` 显式调用便携版流程。
   这是因为 [GITHUB_TOKEN 创建的 Release 不会触发新的 Release 工作流](https://docs.github.com/en/actions/how-tos/write-workflows/choose-when-workflows-run/trigger-a-workflow)。

打包脚本、便携版依赖配置和启动器取自本次工作流的 commit，应用源码取自目标 tag；修复打包流程后可以补打旧 tag。
目标 tag 无需与 `version.json` 的 `tag` 一致。
构建信息仍使用源码中的应用与前端版本，详见[前端版本与分发说明](frontend-releases.md)。
重跑会覆盖同名附件；只需内置 `GITHUB_TOKEN` 的 `contents: write` 权限，无需额外 PAT。

## 前端构建与分发

前端只构建一次，Windows 打包任务直接使用同一轮 CI 的前端制品：

```text
推送 tag / 发布 Release / 手动指定 tag
  └─ 读取构建信息 → 安装锁定依赖（pnpm 缓存）→ 前端测试 → 类型检查与构建
      └─ 打包 frontend-dist.zip + SHA-256 → 保存 Actions artifact
          └─ 上传 GitHub Release（已存在时覆盖同名附件）
              ├─ Windows：下载同一 artifact → 校验 checksum/版本/commit → 便携包
              └─ Jihulab：下载同一 artifact → 校验 checksum → 镜像上传
```

pnpm 版本固定在 `frontend/package.json` 的 `packageManager`，CI 从该字段安装，避免多处维护版本号。
前后端均使用 tag 解析出的同一个 commit，手动执行时也不会混入工作流分支的源码。
同 tag 的发布串行执行，避免并发覆盖附件；Jihulab 镜像失败不会阻断 Windows 任务。
Actions artifact 保留 7 天；期间可用 **Re-run failed jobs** 重试失败的上传或便携包任务，复用已有前端构建。
超过保留期则重新运行整个工作流。
如果修改了工作流或打包工具，应从包含修复的分支执行 **Run workflow** 并填写原 tag；重试旧运行不会载入新修复。

## 构建内容与验证

- 使用 Node.js 22、pnpm 10.26.2 和锁文件执行 `pnpm install --frozen-lockfile`、`pnpm test`、`pnpm run build`。
- 调用前端打包器确认 `build-info.json` 与源码版本一致，同时上传 `frontend-dist.zip` 和 SHA-256；
  将同一份 `frontend/dist` 放入便携包，首次启动无需另行下载前端或安装 Node.js。
- 使用 Python 3.11.9 x64、PyTorch 2.7.0 / torchvision 0.22.0（CUDA 12.8）、xformers 0.0.30，
  安装根 `requirements.txt` 和 ONNX Runtime GPU。额外依赖版本集中在 `.github/portable/requirements.txt`。
- 从 `git archive HEAD` 导出源码，包含 `scripts/dev` 和后端资源；
  不打包本机虚拟环境、模型、数据集、缓存或 Git 凭据。模型和训练数据由用户自行准备。
- 在完整 Python 中构建 wheels，再安装到便携 Python；不直接复制无法可靠搬移的虚拟环境。
  移除嵌入式 Python 的 `._pth` 隔离配置，让训练脚本正常加载自身的 `library`；
  启动器固定 `PYTHONHOME` 到包内，避免加载系统 Python 的注册表路径。
- 检查依赖一致性、CUDA 构建版本、训练入口、GUI 健康接口和静态资源，再创建和测试 7z 压缩包。
  GitHub 托管 runner 没有 NVIDIA GPU，因此这些检查不包含实际 GPU 训练。
- 输出 SHA-256，并在单个附件达到 GitHub 的 2 GiB 上限前报错，避免上传不完整的包。
  压缩前移除三份不参与运行的 Torch 静态构建库，并使用 LZMA2/BCJ2 压缩；保留运行时 DLL。

## 使用

完整解压后，双击 `lora-scripts_windows_portable/run_gui.bat`。启动器会使用包内的
`python/python.exe`，并将工作目录和 Hugging Face 缓存定位到包内。也可在命令行传入 GUI 参数：

```bat
run_gui.bat --listen
```

需要 Windows x64、支持 CUDA 12.8 的 NVIDIA 驱动；无需预装 Python、Node.js 或 CUDA Toolkit。
模型下载和首次生成模型缓存仍可能需要网络。
