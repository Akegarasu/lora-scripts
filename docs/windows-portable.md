# Windows NVIDIA 便携版发布

便携包参考 [ComfyUI 的 Windows 打包流程](https://github.com/Comfy-Org/ComfyUI/blob/master/.github/workflows/windows_release_package.yml)，
使用 Windows runner 构建依赖 wheel、嵌入式 Python 和 7-Zip。每轮同时输出两个包及各自的 SHA-256：

| 附件 | CUDA | PyTorch / torchvision | ONNX Runtime GPU |
| --- | --- | --- | --- |
| `lora-scripts_windows_portable_nvidia.7z`（默认） | 13.0 | 2.14.1 / 0.29.1 | 1.31.1 |
| `lora-scripts_windows_portable_nvidia_cu128.7z`（回退） | 12.8 | 2.11.0 / 0.26.0 | 1.26.0 |

校验文件在对应附件名后追加 `.sha256`。两个包均使用 Python 3.11.9 x64 和 xFormers 0.0.35；xFormers 从各自 CUDA 官方索引获取。
CUDA 13 默认包要求 [R580 或更新驱动](https://docs.nvidia.com/deploy/cuda-compatibility/minor-version-compatibility.html)。
cu128 是 CUDA/驱动兼容回退，两个包的 PyTorch 均要求 Turing 或更新 GPU；[PyTorch 2.11 的 cu128 构建已移除 Volta](https://dev-discuss.pytorch.org/t/dropping-volta-support-from-cuda-12-8-binaries-for-release-2-11/3290)，也不包含 Pascal、Maxwell 支持。

## 触发方式

三个入口统一由 `release-frontend.yml`（**Release frontend and Windows portable**）负责：

1. **发布 Release**：发布正式版或预发布版时，自动构建该 Release 的 tag 并上传附件。
2. **手动补包或重跑**：在 Actions 中选择 **Release frontend and Windows portable** → **Run workflow**，
   选择包含所需代码的分支，填写目标 Release 的已有 Git `tag`。构建使用所选分支在触发时的最新提交，`tag` 只指定上传目标；无需创建新 tag，也不会移动原 tag。Release 不存在时会自动创建。
3. **推送 `v*` tag**：发布前端和 Release 后，通过 `workflow_call` 显式调用便携版流程。
   这是因为 [GITHUB_TOKEN 创建的 Release 不会触发新的 Release 工作流](https://docs.github.com/en/actions/how-tos/write-workflows/choose-when-workflows-run/trigger-a-workflow)。

打包脚本、构建工具依赖和启动器取自本次工作流的 commit；应用源码、根 `requirements.txt` 以及 PyTorch/ONNX 配置均取自本次构建确定的源码提交。
手动运行时，这个提交是所选分支在触发时的最新提交；推送 tag 或发布 Release 时则是对应 tag 的提交。
更新代码或依赖后，选择包含修改的分支并填写原 Release 的 tag，即可覆盖附件。缺少对应 CUDA 配置时，构建会在下载或安装依赖前说明所用源码提交并停止。
目标 tag 无需与 `version.json` 的 `tag` 一致。
构建信息仍使用源码中的应用与前端版本，详见[前端版本与分发说明](frontend-releases.md)。
重跑会覆盖同名附件；只需内置 `GITHUB_TOKEN` 的 `contents: write` 权限，无需额外 PAT。

## 前端构建与分发

前端只构建一次，Windows 打包任务直接使用同一轮 CI 的前端制品：

```text
推送 tag / 发布 Release / 手动选择分支和目标 Release tag
  └─ 读取构建信息 → 安装锁定依赖（pnpm 缓存）→ 前端测试 → 类型检查与构建
      └─ 打包 frontend-dist.zip + SHA-256 → 保存 Actions artifact
          └─ 上传 GitHub Release（已存在时覆盖同名附件）
              ├─ Windows cu130：下载同一 artifact → 校验 checksum/版本/commit → 默认便携包
              ├─ Windows cu128：下载同一 artifact → 校验 checksum/版本/commit → 回退便携包
              └─ Jihulab：下载同一 artifact → 校验 checksum → 镜像上传
```

pnpm 版本固定在 `frontend/package.json` 的 `packageManager`，CI 从该字段安装，避免多处维护版本号。
前端和两个 Windows 包均使用本次构建确定的同一个 commit；任务执行期间分支继续更新也不会混入后续提交。
同 tag 的发布串行执行，避免并发覆盖附件。Windows 使用同一轮 matrix，设置 `fail-fast: false`；一个 CUDA 包失败不会取消另一个包，附件名也不会互相覆盖。Jihulab 镜像失败不会阻断 Windows 任务。
Actions artifact 保留 7 天；期间可用 **Re-run failed jobs** 重试失败的上传或便携包任务，复用已有前端构建。
超过保留期则重新运行整个工作流。
如果修改了工作流或打包工具，应从包含修复的分支执行 **Run workflow** 并填写原 tag；重试旧运行不会载入新修复。

## 构建内容与验证

- 使用 Node.js 22 LTS（至少 22.12）、`packageManager` 固定的 pnpm 和锁文件执行 `pnpm install --frozen-lockfile`、`pnpm test`、`pnpm run build`。
- 调用前端打包器确认 `build-info.json` 与源码版本一致，同时上传 `frontend-dist.zip` 和 SHA-256；
  将同一份 `frontend/dist` 放入便携包，首次启动无需另行下载前端或安装 Node.js。
- 使用上表中的两组 GPU 运行时，安装根 `requirements.txt` 中的应用与训练依赖。
  PyTorch/torchvision/xFormers 版本集中在 `requirements/pytorch-cu130.txt` 和 `requirements/pytorch-cu128.txt`；
  ONNX Runtime 分别由 `requirements/onnxruntime-cu130.txt`、`requirements/onnxruntime-cu128.txt` 管理，构建工具由 `requirements/tooling.txt` 管理。
- 从所选 PyTorch 官方 CUDA 索引获取 PyTorch、torchvision 和 xFormers，再安装通用依赖，避免同名 xFormers wheel 混入另一种 CUDA 构建。
- 从 `git archive HEAD` 导出源码，包含 `scripts/dev` 和后端资源；
  不打包本机虚拟环境、模型、数据集、缓存或 Git 凭据。模型和训练数据由用户自行准备。
- 在完整 Python 中构建 wheels，再安装到便携 Python；不直接复制无法可靠搬移的虚拟环境。
  移除嵌入式 Python 的 `._pth` 隔离配置，让训练脚本正常加载自身的 `library`；
  启动器固定 `PYTHONHOME` 到包内，避免加载系统 Python 的注册表路径。
- 检查依赖一致性、CUDA 构建版本、训练入口、GUI 健康接口和静态资源，再创建和测试 7z 压缩包。
  GitHub 托管 runner 没有 NVIDIA GPU，因此这些检查不包含实际 GPU 训练。
- 输出 SHA-256，并在单个附件达到 GitHub 的 2 GiB 上限前报错，避免上传不完整的包。
  压缩前移除三份不参与运行的 Torch 静态构建库，并使用 LZMA2/BCJ2 压缩；保留运行时 DLL。

2026-11-03 的本地验证中，两组依赖均在嵌入式 Python 3.11.9 下通过 `pip check`、GPU 库导入、训练入口、CPU 优化器步骤及 GUI/前端检查。
该验证将独立环境中已安装的依赖复制到临时便携目录，用于检查嵌入式运行时和压缩体积；尚未在 GitHub Actions 执行完整的 wheel 构建与离线安装流程。
使用与发布脚本相同的压缩参数，cu130 验证包为 1,857,112,690 bytes（约 1.73 GiB），cu128 为 1,870,451,033 bytes（约 1.74 GiB）；
两包均通过 `7z t` 完整性检查且低于单附件上限，无需分卷。验证包包含额外的 ONNX 测试依赖，实际 CI 产物大小可能略有差异。

## 使用

完整解压后，双击 `lora-scripts_windows_portable/run_gui.bat`。启动器会使用包内的
`python/python.exe`，并将工作目录和 Hugging Face 缓存定位到包内。也可在命令行传入 GUI 参数：

```bat
run_gui.bat --listen
```

包内 `runtime-info.json` 记录当前 CUDA 配置和 Python 版本，`installed-packages.txt` 记录实际安装的依赖版本。

需要 Windows x64、满足所选包要求的 NVIDIA GPU 和驱动；无需预装 Python、Node.js 或 CUDA Toolkit。
模型下载和首次生成模型缓存仍可能需要网络。
