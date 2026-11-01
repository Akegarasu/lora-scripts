# sd-scripts 上游快照

本目录同步自 [kohya-ss/sd-scripts v0.12.3](https://github.com/kohya-ss/sd-scripts/commit/cb70b96858477e716a2096292ab8aab433277f38)，
提交时间为 2026-10-26 13:11:08 UTC，2026-11-01 核对时为 `main` 最新提交。
可供工具读取的来源信息保存在 `UPSTREAM.json`，参数清单生成器会将其写入 manifest。

## 同步基线与范围

- 原有 238 个受 Git 跟踪的上游文件，规范化 CRLF 后全部与 v0.12.0
  `690ea7f96c23182352ec63def76d431c6120bd2f` 一致，没有本地代码补丁。
- 本轮上游文件新增 13 个、修改 59 个、删除 0 个；另更新本说明与 `UPSTREAM.json`。
- 沿用现有 vendoring 范围，排除上游 `.ai/`、`.github/`、`tests/`，不收录 Python 字节码。
- 全部 251 个同步文件已与固定提交归档逐文件核对；`scripts/stable` 保持原有快照。
- 本次使用正式版 `main`，不合并尚未发布的 `dev` 变更。

## 本轮主要变化

- 新增 MOSS-Image Base / SFT 的 DiT 及可选文本编码器 LoRA 训练，使用
  `moss_image_train_network.py` 和 `networks.lora_generic`，模型组件为 Qwen3.5-9B 与 FLUX.2 VAE。
  模型文件、量化和缓存的限制见 [MOSS-Image 训练指南](./docs/moss_image_train_network.md)。
- 新增 ConvRot INT8 量化，以及相应的加载、推理、latent 和文本编码器缓存工具。
- FLUX.1 / Chroma、Lumina、HunyuanImage、Anima、MOSS-Image LoRA 支持
  `block_swap_h2d_only`；需要 `gradient_checkpointing`，不支持 SD3。
  参见 [Block Swap 指南](./docs/block_swap.md)。
- 支持多行 Caption 和多个候选 Caption；MOSS-Image 支持将所有候选文本输出缓存到同一文件。
- 新增 `truncated_logit_normal` 时间步采样，及 `timestep_cutoff`、`timestep_uniform_ratio` 参数。
- 修复文本缓存未应用 Caption 前后缀等预处理的问题。使用旧版本生成的磁盘文本缓存时，
  如曾使用 `caption_prefix` / `caption_suffix`、`secondary_separator` 或多行 Caption，
  应删除对应旧 `*_te.npz` 等缓存并重新生成；详见 [上游变更记录](./README.md#change-history)。

## 依赖与验证边界

本目录 `requirements.txt` 原样保留上游推荐版本；从 v0.12.0 到 v0.12.3 没有变化：

| 依赖 | 上游推荐版本 |
| --- | --- |
| accelerate | 1.15.0 |
| transformers | 5.17.0 |
| diffusers | 0.40.0 |
| huggingface-hub | 1.32.0 |
| safetensors | 0.8.0 |
| schedulefree | 1.4.1 |

上游要求 PyTorch 2.6 或更新版本。MOSS-Image 文本编码器实际依赖
`transformers.Qwen3_5TextConfig` / `Qwen3_5TextModel`，仅能导入训练 parser
不代表旧版 transformers 已支持该模型。ConvRot INT8 的融合内核和 INT8 backward
需要 Triton（Windows 使用 triton-windows）；没有 Triton 时，默认 bf16 backward
路径仍可使用量化权重，但前向会临时反量化。

本项目环境由根目录依赖文件控制；同步源码不会自动升级已安装的 Python 环境。
源码一致性检查不代表所有精度、量化或编译组合已经完成真实模型训练验证。

重新生成参数清单：

```powershell
.\venv\Scripts\python.exe -m mikazuki.catalog.inspector generate --scripts-root scripts/dev
```

后续同步应先验证本地与 `UPSTREAM.json` 所指快照的差异，再更新来源记录和 manifest，
避免把本地适配误当作上游文件覆盖。
