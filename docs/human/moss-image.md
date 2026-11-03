# MOSS-Image 配置

本工作台提供 `moss_image.lora`，使用仓库内的 sd-scripts 快照。完整模型说明见[上游 MOSS-Image 文档](../../scripts/dev/docs/moss_image_train_network.md)，来源版本见 [UPSTREAM.md](../../scripts/dev/UPSTREAM.md)。

## 环境

使用[项目安装器](../../README-zh.md#从源码安装)与根 `requirements.txt`，不要只更新训练源码而保留旧依赖。MOSS-Image 依赖 Transformers 的 `Qwen3_5TextConfig`/`Qwen3_5TextModel`；能够读取 parser 不等于运行时支持模型。

旧环境升级发生依赖冲突时，保留原 venv，另建环境安装。默认 cu130、可选 cu128 的具体版本由 `requirements/pytorch-*.txt` 和 `requirements/onnxruntime-*.txt` 管理。已有兼容 PyTorch 时，安装器可使用 `-SkipTorch`（Windows）或 `--skip-torch`（Linux）。

Triton、Flash Attention 和 flash-linear-attention 不是默认路径的必需依赖。默认使用 PyTorch attention；ConvRot INT8 在没有 Triton 时可采用较慢的 bf16 反量化回退，选择 `convrot_int8_bwd=int8` 才需要 CUDA 与匹配的 Triton，Windows 对应 triton-windows。可选内核和 torch.compile 按上游文档配套安装。

## 模型与训练配置

1. 选择 **MOSS-Image LoRA**，准备 MOSS-Image Base/SFT DiT、Qwen3.5-9B 文本编码器、FLUX.2 VAE。
2. 官方分片权重选择第一个 `.safetensors`，其余分片放在同一目录；也可使用上游支持的 ComfyUI 单文件。Qwen W4A8 GPTQ 文件不受支持。
3. 填写数据集与输出位置，bucket 步长须为 16 的倍数。默认 DiT-only、bf16、latent 缓存与文本输出缓存；以界面中的当前默认值和校验结果为准。
4. 训练文本编码器时关闭“仅训练 DiT”及两项文本缓存。文本编码器使用 bf16，VAE 使用 fp32；不要使用通用 `fp8_base`，量化路径为 ConvRot INT8。
5. H2D-only block swap 需要 gradient checkpointing 与启用的 block swap；不同配置的显存与速度需实际测量。
6. 预览并检查配置后启动训练。配置导出与运行时校验是两步；导出成功不能证明当前依赖和 GPU 可运行。

多行/多候选 Caption 使用上游支持的分隔行 `---===---`；在当前训练器参数中启用对应选项。MOSS-Image 可缓存全部候选文本输出，候选越多，首次编码和缓存开销越大。

Tokenizer 默认从 `OpenMOSS-Team/MOSS-Image-Base` 下载。离线使用时，设置 `tokenizer_cache_dir` 为已有 tokenizer 文件的目录。

使用旧版缓存并曾设置 caption 前后缀、secondary separator 或多行 Caption 时，按 [UPSTREAM.md](../../scripts/dev/UPSTREAM.md) 核对是否需要重建文本缓存。不要把局部算子测试或历史验证记录当成当前完整训练已通过的证明。
