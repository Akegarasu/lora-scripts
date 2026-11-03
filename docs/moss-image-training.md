# MOSS-Image 训练

本项目的 `scripts/dev` 同步到 [sd-scripts v0.12.3](https://github.com/kohya-ss/sd-scripts/commit/cb70b96858477e716a2096292ab8aab433277f38)。工作台新增 **MOSS-Image LoRA**，支持 Base / SFT 底模、DiT LoRA，以及关闭文本缓存后的文本编码器 LoRA。模型和显存策略详见[上游训练指南](../scripts/dev/docs/moss_image_train_network.md)。

## 安装依赖

本项目统一使用根目录 `requirements.txt` 中的依赖：accelerate 1.15.0、transformers 5.20.2、diffusers 0.41.0、huggingface-hub 1.33.0、safetensors 0.8.0、schedulefree 1.4.1。已有环境也需要升级；MOSS-Image 的 Qwen3.5 文本编码器不能使用原有 Transformers 4.54.1。

默认 CUDA 13.0 配置需要 Python 3.11 或更高版本；Python 3.10 源码环境可选择 cu128。两种配置分别保存在 `requirements/pytorch-cu130.txt` / `pytorch-cu128.txt`，ONNX Runtime 对应 `requirements/onnxruntime-cu130.txt` / `onnxruntime-cu128.txt`；安装工具版本在 `requirements/tooling.txt`。自备运行时的 PyTorch 至少需要 2.6。

两种官方 Linux GPU 配置要求 glibc 2.28 或更新版本。自动准备 ONNX Runtime 支持 CUDA 12.8+、CUDA 13 和 CPU；
自备更旧的 CUDA 环境时，需通过 `ONNXRUNTIME_VERSION` 指定兼容版本，或使用 `--skip-prepare-onnxruntime` 自行维护。
已移除与 NumPy 2 不兼容的旧 glibc → ONNX Runtime 1.16.3 自动降级。

应用依赖一并迁移至 FastAPI 0.162、Pydantic 2.14.2、httpx 0.28 和 NumPy 2.2.6，移除了默认流程不再需要的 pytorch-lightning、open-clip-torch 和 pandas。应将代码与依赖一起升级；手动发布时选择包含配套迁移的分支，可将新构建上传到已有 Release，无需新建 tag。推送 tag 和发布 Release 事件仍构建对应 tag 的源码。

从旧依赖栈迁移时建议保留原 `venv`，另建 Python 3.11 环境再运行安装器。仅更新 requirements 不会自动移除旧环境中的 open-clip-torch 等遗留包，它们对旧 protobuf 的约束可能与新依赖冲突。

从项目根目录执行以下命令，创建或更新当前项目的 `venv`。国内安装器若发现 `python/python.exe`，则使用该内置 Python。GUI 与训练进程使用同一个 Python。

Windows：

```powershell
.\scripts\install.ps1
# 国内 PyPI 镜像：
.\scripts\install-cn.ps1
```

Linux：

```bash
bash scripts/install.bash
```

安装器默认提供 PyTorch 2.14.1、torchvision 0.29.1、xFormers 0.0.35 与 CUDA 13.0，并安装 ONNX Runtime GPU 1.31.1。使用 CUDA 12.8 回退配置时，PyTorch/torchvision 为 2.11.0/0.26.0，ONNX Runtime 为 1.26.0（Python 3.10 使用 1.23.2）：

```powershell
.\scripts\install.ps1 -Cuda cu128
# 国内安装器也支持 -Cuda cu128
```

```bash
bash scripts/install.bash --cuda cu128
```

两种配置的 xFormers 均从对应的 CUDA 官方索引获取。CUDA 13 需要 R580 或更新驱动；cu128 提供不同的 CUDA/驱动组合，但两组 PyTorch 均要求 Turing 或更新显卡，不恢复 Pascal、Volta 支持。详见[便携包兼容说明](windows-portable.md)。其他 CUDA/硬件组合请先在项目环境安装匹配的 PyTorch >= 2.6 和 torchvision，参考 [PyTorch 官方安装说明](https://pytorch.org/get-started/locally/)，然后保留已安装的 PyTorch：

```powershell
.\scripts\install.ps1 -SkipTorch
```

```bash
bash scripts/install.bash --skip-torch
```

已有合适 PyTorch 环境也可直接安装；执行前请确认使用的 Python 正是启动 GUI 的解释器：

```powershell
.\venv\Scripts\python.exe -m pip install --upgrade -r requirements.txt
.\venv\Scripts\python.exe -c "import torch; from transformers import Qwen3_5TextConfig, Qwen3_5TextModel; print(torch.__version__)"
```

Linux 使用 `venv/bin/python`。安装完成后重新启动 GUI。

GUI 启动时统一核对根目录 `requirements.txt`，并按已安装 PyTorch 的 CUDA 版本选择 ONNX Runtime，避免在 cu128 环境中安装默认 CUDA 13 的新版 ONNX 包。若 PyTorch 低于 2.6，启动器会提示先运行安装器或安装匹配显卡的 PyTorch。`--skip-prepare-environment` 可用于已准备好的环境，跳过启动时的依赖准备，但不会使旧依赖具备 MOSS-Image 训练能力。

Triton、Flash Attention 和 `flash-linear-attention` 均不是默认训练的必需依赖。MOSS-Image 默认使用 PyTorch attention；没有 Triton 时，ConvRot INT8 可使用较慢的 bf16 反量化回退。选择 `convrot_int8_bwd=int8` 时需要 CUDA 和匹配 PyTorch 版本的 Triton；Windows 使用 `triton-windows`。`torch.compile` 及可选加速内核请按[上游说明](../scripts/dev/docs/moss_image_train_network.md#71-vram-usage-optimization--vram-使用量の最適化)安装，不要直接混装不匹配的二进制包。

## 工作台配置

1. 选择 **MOSS-Image LoRA**。
2. 提供 MOSS-Image DiT、Qwen3.5-9B 文本编码器和 FLUX.2 VAE。官方分片权重应选择第一个 `.safetensors` 文件，并将其余分片放在同一目录；也可使用上游支持的 ComfyUI 单文件。Qwen 的 W4A8 GPTQ 文件不受支持。
3. 配置数据集和输出目录。分桶分辨率步长须为 16 的倍数。默认使用 DiT-only、bf16、latent 缓存和文本输出缓存；更改高级选项时注意工作台报告的冲突。
4. 需要保留 Caption 中换行或提供多个候选 Caption 时，启用数据集的多行 Caption，使用分隔行 `---===---` 区分候选。MOSS-Image 可以缓存所有候选的文本编码结果；缓存大小和首次编码时间随候选数量增加。
5. 预览配置并启动训练。配置导出与运行时检查分开；开始任务时会检查 MOSS-Image 所需运行时版本。

训练文本编码器时须关闭“仅训练 DiT”以及两项文本缓存选项。文本编码器固定使用 bf16，VAE 使用 fp32；`fp8_base` 不适用于此模型，低显存量化请使用 ConvRot INT8。H2D-only block swap 需要 gradient checkpointing，通常与 `blocks_to_swap` 配合。上述选项会影响速度和显存，不代表已验证每种组合的训练质量。

Tokenizer 默认从 `OpenMOSS-Team/MOSS-Image-Base` 下载。离线使用时，设置 `tokenizer_cache_dir` 指向包含 tokenizer 文件的本地目录。

## 验证范围

2026-11-03 在独立的 Python 3.11.14 环境分别安装了上表中的 cu130 和 cu128 配置，均通过 `pip check`。
两组均在 RTX 4090 / 驱动 621.01 上通过 CUDA 前后向、xFormers FP16 Attention 前后向、bitsandbytes Adam8bit 更新和 ONNX Runtime CUDA MatMul 推理；
ONNX 检查关闭 TF32 与 CPU 回退，并通过 profiling 确认节点运行于 CUDA。两个配置的微型 Qwen3.5 CPU 前后向也通过。
这些是小规模运行时检查，不是完整模型的数据集训练。

新版 cu130 环境的后端测试 243 项中 240 项通过、3 项跳过，9 个训练入口的导入、生成配置读取和数据集 blueprint 检查通过；
前端 11 项测试、类型检查、生产构建及锁定安装通过。
两组依赖在 Windows / Linux 的 Python 3.11 上完成解析，cu128 另验证了 Python 3.10 / Windows 解析。
Docker 配置已核对，但未执行镜像构建。

下面保留的是 **2026-11-01 的历史验证记录**，对应升级前的运行时，不能据此认为当前 CUDA 13 / CUDA 12.8 双配置已完成 GPU 训练验证。

2026-11-01 已在本项目 `venv` 中实际安装当时的统一依赖，包括 PyTorch 2.7.0+cu128、torchvision 0.22.0+cu128、xFormers 0.0.30、transformers 5.17.0、diffusers 0.40.0 和 huggingface-hub 1.32.0。`pip check` 未发现依赖冲突，CUDA 12.8 正确识别 RTX 4090；GUI 与 Caption 适配器导入通过。

升级后的后端测试 226 项：224 通过、2 项因 Windows 符号链接权限跳过。移除了已取消的依赖分档测试，并将 Qwen3 Caption 可用性测试改为显式覆盖新旧版本边界。全部 9 个训练入口的真实导入、工作台生成 TOML 的上游读取、数据集 blueprint 和 MOSS 多行采样提示解析通过。前端 11 项测试、类型检查与生产构建也已通过。

新版环境的 48 项针对性检查全部通过，包括 RTX 4090 上微型 MOSS DiT LoRA 的 BF16 前向、梯度检查点、反向传播与 AdamW 更新，xFormers CUDA Attention 及梯度，bitsandbytes AdamW8bit 的 CUDA 内核及 uint8 优化器状态，以及上游 CLIP 兼容、微型 Qwen3.5 LoRA、FLUX.2 VAE 转换和 MOSS 缓存检查。未据此宣称所有 Triton 或 torch.compile 组合均已验证。

既有 8 个训练器的训练参数 `effectiveDefault` 均保持不变，MOSS 新建采样预览使用上游的 50 步、CFG 3，已保存的用户采样配置不会被覆盖。

当时的依赖配置通过 Windows / Python 3.10 的依赖解析，包括 PyTorch 2.7.0 / torchvision 0.22.0 组合。FastAPI 0.95.1 和 httpx 0.24.1 与当时 Hugging Face Hub 的声明依赖兼容，因此那次升级没有迁移 GUI 依赖栈；当前配置已按前文更新。

此前还在隔离目录中使用 PyTorch 2.6.0 CPU、torchvision 0.21.0 和新版 Hugging Face 库，完成 9 个训练入口的配置读取和微型 Qwen3.5 前向、反向检查。MOSS parser 包含 235 个 argparse action（包括 help），目录收录 234 个参数。

在原有 PyTorch 2.4.1 环境另执行上游 CPU 测试：170 项通过、9 项跳过、5 项排除、2 项失败。失败项分别为 ConvRot 浮点 scale 严格相等断言（INT8 权重相同，scale 最大绝对差为 `2.91e-10`），以及旧版 PyTorch Dynamo 的 CUDA 探测导致的 compile 失败。未为绕过这些测试修改上游代码；这些结果不代表 GPU 编译或量化内核已验证。

2026-11-01 核对过当时的 PyTorch 2.7.0 / CUDA 12.8 Docker 镜像标签、源文件路径和依赖入口，未实际执行 Docker 镜像构建。当前 Docker 默认使用 PyTorch 2.14.1 / CUDA 13.0，cu128 构建方法见 [README](../README-zh.md#docker)；历史核对结果不等同于新镜像构建验证。

未下载真实训练权重，未执行完整预训练模型的数据集训练；微型网络检查不能替代实际模型训练质量与显存需求验证。
