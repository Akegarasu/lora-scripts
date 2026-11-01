# sd-scripts 参数目录审查

调查日期：2026-09-28。核对版本为上游 main 的 [v0.12.0，`690ea7f96c23182352ec63def76d431c6120bd2f`](https://github.com/kohya-ss/sd-scripts/commit/690ea7f96c23182352ec63def76d431c6120bd2f)，发布于 2026-09-24。范围包括通用 LoRA、SD/SDXL，以及 Flux、Chroma、SD3、Lumina、HunyuanImage、Anima 的参数目录与说明。

## 分级原则

`priority` 决定参数在界面中的曝光程度，**不表示自动启用参数，也不表示推荐某个数值**。本次保持全部已有 `effectiveDefault` 不变；新登记的实验项也不增加 `effectiveDefault`。

| 分级 | 本项目的含义 |
| --- | --- |
| `required` | 基础视图显示；编译器也将其视为必填，应只用于确实需要用户提供的输入。 |
| `recommended` | 基础视图显示，便于常见训练决策；不代表必须启用。 |
| `advanced` | 高级视图显示，供按模型、优化器或训练目的调整。 |
| `dangerous` | 高级视图显示并提示具体后果，例如只输出诊断后退出训练。 |
| `hidden` | 常规和高级视图隐藏；`all` 视图仍可读取，用于结构化入口已接管或当前训练器不使用的参数。 |

证据按“当前实现与模型约束、维护者答复、实际应用、个人实验”区分。历史 issue 的报错不直接视为当前 bug；文档与代码冲突时核对实际训练入口。公开配置能够说明使用方式，不能证明一套学习率、rank、alpha 或训练步数普遍最优。

## 证据记录

下表日期是讨论或修复发生日期；标注“访问日”的文档和应用指本次读取的公开版本，不冒充发布日期。

| 一手来源 | 日期、适用范围 | 本次采用的证据与限制 |
| --- | --- | --- |
| [官方 Discussion #683：8GB SDXL](https://github.com/kohya-ss/sd-scripts/discussions/683) | 2023-07-27～28；SDXL 低显存训练 | 维护者建议 AdamW8bit，并指出 `full_fp16` 稳定性和 VAE 半精度 NaN 问题；支持突出常用显存选项与 `no_half_vae`，不复制帖子中的完整配方。 |
| [官方 Issue #886：文本编码器缓存](https://github.com/kohya-ss/sd-scripts/issues/886)；[当前 SDXL 入口](https://github.com/kohya-ss/sd-scripts/blob/690ea7f96c23182352ec63def76d431c6120bd2f/sdxl_train_network.py) | 2023-10-18；当前代码复核 | 缓存文本输出与动态 caption 操作、文本编码器训练互斥，当前断言仍存在；issue 关闭不代表该约束消失。 |
| [官方 Issue #1952](https://github.com/kohya-ss/sd-scripts/issues/1952)；[修复 PR #1964](https://github.com/kohya-ss/sd-scripts/pull/1964) | 2025-02-25 报告，2025-03-21 合并修复；SDXL 文本编码器 | CLIP attention 类名变化曾导致部分 LoRA 模块未训练，已经修复；不能据此将当前 SDXL 文本编码器训练描述为不支持。 |
| [官方 PR #1717：移除过时的 v-pred 警告](https://github.com/kohya-ss/sd-scripts/pull/1717) | 2024-10-25 合并到 dev；模型预测类型 | SDXL 也存在 v-pred 模型。修正“仅 SD1/2 使用”的笼统警告，但仍要求与底模预测类型匹配。 |
| [官方 Discussion #772：恢复训练](https://github.com/kohya-ss/sd-scripts/discussions/772)；[高级训练文档](https://github.com/kohya-ss/sd-scripts/blob/690ea7f96c23182352ec63def76d431c6120bd2f/docs/train_network_advanced.md) | 2023-08-20 起；文档访问日 2026-09-28 | 用户会混淆权重加载、状态恢复和显示步数。保留恢复训练的高级说明；个人报告不足以证明当前 resume 失效或逐位可复现。 |
| [kohya_ss GUI 参数指南](https://github.com/bmaltais/kohya_ss/blob/master/docs/LoRA/options.md) | 访问日 2026-09-28；以传统 SD LoRA 为主 | batch、epoch、保存间隔、优化器、LR/scheduler/warmup、dim/alpha 都是常规决策；自定义优化器和 scheduler 参数适合高级入口。不沿用旧指南中的固定轮数或 LR 经验公式。 |
| [hollowstrawberry SD 训练 notebook](https://github.com/hollowstrawberry/kohya-colab/blob/main/Lora_Trainer.ipynb)；[SDXL notebook](https://github.com/hollowstrawberry/kohya-colab/blob/main/Lora_Trainer_XL.ipynb) | 访问日 2026-09-28；实际生成训练配置的外部应用 | 均提供 UNet/文本编码器 LR、warmup、Min-SNR 等设置；XL 明确处理文本缓存与训练、shuffle 的互斥。两者 Min-SNR 配方不同，支持常显该选项，不支持统一改默认值。 |
| [官方 Flux Issue #1454 维护者答复](https://github.com/kohya-ss/sd-scripts/issues/1454#issuecomment-2291284416)；[FluxGym 实际代码](https://github.com/cocktailpeanut/fluxgym/blob/main/app.py) | issue 始于 2024-08-14；应用访问日 2026-09-28 | 维护者的 FP8、缓存建议与实际应用互相印证；将 Flux 的 `fp8_base` 视为常用显存决策，不将早期加载报错当作当前缺陷。 |
| [官方 Chroma Issue #2163 维护者答复](https://github.com/kohya-ss/sd-scripts/issues/2163#issuecomment-3144467286)；[Chroma Training UI 配置](https://github.com/r0wer/chroma-training-ui/blob/10e17b1b0dab70910ec3d111ba42e9d04b959b6a/train.sh) | issue 始于 2025-07-31；应用为固定提交 | T5 attention mask 是 Chroma 的模型约束，应保留明确说明；外部训练入口也提供模型专属显存配置。不能将该约束泛化到所有 Flow 模型。 |
| [官方 SD3 Issue #1802 维护者实验](https://github.com/kohya-ss/sd-scripts/issues/1802#issuecomment-2495983307) | issue 始于 2024-11-21；SD3.5L | 维护者实际使用 `fp8_base`，支持 SD3 中常显；实验中的高学习率不作为通用默认值。 |
| [官方 HunyuanImage LoRA 指南](https://github.com/kohya-ss/sd-scripts/blob/690ea7f96c23182352ec63def76d431c6120bd2f/docs/hunyuan_image_train_network.md) | 访问日 2026-09-28；HunyuanImage-2.1 | 明确介绍 scaled FP8、block swap 和文本编码器 CPU 编码的显存用途及速度代价；其 FP8 入口是 `fp8_scaled`，不能机械套用 `fp8_base`。 |
| [官方 Lumina Issue #2201](https://github.com/kohya-ss/sd-scripts/issues/2201)；[Anima Issue #2363](https://github.com/kohya-ss/sd-scripts/issues/2363) | 分别始于 2025-09-16、2026-05-28 | Lumina 的个人报告不足以形成通用配方；Anima 回帖中的 shift 1.5 属于非维护者个人实验。保留模型差异说明，不据此改默认值或扩大 FP8 推荐范围。 |
| [Flux/Chroma scaled FP8 PR #2208](https://github.com/kohya-ss/sd-scripts/pull/2208) | 2026-09-28 核查时仍 open | 提案不能当作当前 main 已支持的功能，本次不为 Flux/Chroma 添加 `fp8_scaled` 支持。 |

## 本次分级决策

| 范围 | 参数与处理 | 理由 |
| --- | --- | --- |
| 通用训练 | `max_train_steps`、`save_every_n_steps`、`gradient_accumulation_steps`、`lr_warmup_steps` → `recommended` | 分别控制训练量、检查点间隔、有效 batch 和学习率预热，属于常见训练决策。 |
| 通用网络 | `network_module` → `advanced`，同时 `required: false` | 模型族已经提供默认网络模块；仍保留高级覆盖入口，避免让用户把内部模块名当作必填项。 |
| 通用保存与日志 | `save_model_as`、`save_precision`、`max_grad_norm`、`logging_dir` → `advanced` | 已有默认值覆盖普通使用，主要在兼容性、优化器配套或日志集成时调整。 |
| SD/SDXL | `unet_lr`、`text_encoder_lr`、`min_snr_gamma` → `recommended` | 实际训练应用常暴露这些决策；文本编码器是否训练仍受缓存等约束。 |
| SDXL | `no_half_vae` → `recommended`；`v_parameterization` → `advanced` 并纠正说明 | 前者处理常见 VAE 数值稳定性问题；后者应由底模类型决定，不再宣称 SDXL 一律不能使用。 |
| FP8 | 通用 `fp8_base` → `advanced`；仅 Flux、Chroma、SD3 override 为 `recommended` | 显存收益、实现与证据均依赖模型。Lumina 保持 `advanced`，不把通用继承当作普遍推荐。 |
| HunyuanImage | `fp8_scaled`、`blocks_to_swap`、`text_encoder_cpu` → `recommended` | 官方说明和显存使用场景明确；常显便于取舍，不自动启用，也不承诺固定显存或速度。 |
| Flow | 固定使用 `raw` 的 `model_prediction_type`、训练参数 `guidance_scale` → `advanced`；SD3 `t5xxl_max_token_length` → `advanced` | 默认工作流通常不需修改；训练 guidance 不能与预览采样 CFG 混为一谈。 |
| Flow 优化目标 | `unet_lr`、`network_train_unet_only` → `advanced`；Lumina/HunyuanImage `discrete_flow_shift` → `advanced` | 默认 DiT-only 配方通过总学习率控制训练，分支学习率和目标选择留在高级入口；固定 shift 数值也无需每次修改。SD/SDXL 仍常显 UNet/文本编码器训练选择。 |
| Anima LoRA | `self_attn_lr`、`cross_attn_lr`、`mlp_lr`、`mod_lr`、`llm_adapter_lr` → `hidden` | 五项属于全量微调入口，在 LoRA 路径无效；LoRA 模块分组 LR 使用 `network_args` 的 `network_reg_lrs`。`all` 视图保留读取。 |
| 新增诊断/实验项 | FLUX/Chroma/Anima `show_timesteps` → `dangerous`；Anima compile、Qwen2D VAE 实验项 → `advanced` | 支持预览的入口展示时间步后退出，不执行训练；SD3/Lumina/HunyuanImage 虽解析该参数却仍会开始训练，隐藏其三个预览字段。实验项仅补目录和说明，不新增 `effectiveDefault`。 |
| 其余常用项 | 优化器、基础 LR/scheduler、dim/alpha、batch/epoch、常用缓存保持现有基础入口；自定义 optimizer/scheduler/network args、增强/dropout、复杂噪声策略、state/resume 保持高级入口 | 频繁决策应易发现，模型或策略相关选项应说明适用条件；不把某个公开配方提升为通用默认。数据集 repeats 和采样内容继续由各自结构化入口管理，避免重复控制。 |

## 需要保留的语义与约束

- 上游使用 `max_train_epochs` 时会覆盖 `max_train_steps`；本工作台对两者同时显式设置报冲突，按步训练应清空 Epoch。repeat、batch、梯度累积共同影响实际更新次数，常显两种控制不表示两者同时独立生效。
- 文本缓存约束需逐模型判断：SDXL 不允许同时训练文本编码器；FLUX/SD3 支持训练 CLIP LoRA 时仅缓存 T5，但训练 T5 LoRA 必须关闭文本缓存。Anima 支持整体 Caption dropout 缓存，仍禁止 shuffle、tag dropout、token warmup，修改整体 dropout 比例后需重建缓存。依据为当前 [FLUX 入口](https://github.com/kohya-ss/sd-scripts/blob/690ea7f96c23182352ec63def76d431c6120bd2f/flux_train_network.py)、[SD3 入口](https://github.com/kohya-ss/sd-scripts/blob/690ea7f96c23182352ec63def76d431c6120bd2f/sd3_train_network.py) 与 [Anima 入口](https://github.com/kohya-ss/sd-scripts/blob/690ea7f96c23182352ec63def76d431c6120bd2f/anima_train_network.py)。
- latent 缓存与 `color_aug`、`random_crop` 冲突，但支持 `flip_aug`，不能复制旧文档“禁止所有增强”的说法。依据为当前 [dataset](https://github.com/kohya-ss/sd-scripts/blob/690ea7f96c23182352ec63def76d431c6120bd2f/library/dataset.py)、[caching](https://github.com/kohya-ss/sd-scripts/blob/690ea7f96c23182352ec63def76d431c6120bd2f/library/caching.py) 和各训练器断言。
- Chroma 可以关闭 DiT-only 并用 `network_args train_t5xxl=True` 训练 T5 LoRA，需同时关闭文本缓存及磁盘缓存；不能将默认 DiT-only 配方写成“不支持 T5 训练”。FLUX/Chroma/Anima/HunyuanImage 以及 Lumina 的 `discrete_flow_shift` 在 `sigma` 或 `shift` 采样下生效，`flux_shift` / `nextdit_shift` 使用各自的分辨率偏移。已核对 [FLUX 采样实现](https://github.com/kohya-ss/sd-scripts/blob/690ea7f96c23182352ec63def76d431c6120bd2f/library/flux_train_utils.py) 与 [Lumina 实现](https://github.com/kohya-ss/sd-scripts/blob/690ea7f96c23182352ec63def76d431c6120bd2f/library/lumina_train_util.py)。
- Min-SNR、noise offset、多分辨率噪声和 v-pred 损失策略各有适用范围；SD/SDXL 的常用选项不能直接推导成 Flow 模型的推荐配方。
- Prodigy、Adafactor 等优化器的 LR、scheduler、预热和 clipping 需要配套；不同优化器中同一数值不一定具有相同含义。保持 args 高级可编辑，不加入“一键最佳参数”。
- 加载 `network_weights` 与 `save_state`/`resume` 恢复训练状态是不同操作；保存模型精度也不同于训练混合精度。采样频率和检查点频率用于观察训练进展，不证明生成质量。
- Anima 的分层 LR 归属已核对 [全量训练入口](https://github.com/kohya-ss/sd-scripts/blob/690ea7f96c23182352ec63def76d431c6120bd2f/anima_train.py) 与 [LoRA 网络实现](https://github.com/kohya-ss/sd-scripts/blob/690ea7f96c23182352ec63def76d431c6120bd2f/networks/lora_anima.py)，不因共享 parser 能解析参数就声称 LoRA 会使用它。

## 验证边界与依赖

本次从真实 `setup_parser()` 重新生成 catalog；SD/SDXL 参数数量不变，6 个 Flow 训练器各新增 3 个诊断参数，Anima 另新增 9 个编译与 VAE 参数。上游文件与固定提交的内容核对一致；来源记录见 [UPSTREAM.md](../scripts/dev/UPSTREAM.md)，manifest 包含上游 SHA 并将其纳入 hash。

共享 parser 不等于训练入口实际支持：时间步预览仅在 [FLUX/Chroma 入口](https://github.com/kohya-ss/sd-scripts/blob/690ea7f96c23182352ec63def76d431c6120bd2f/flux_train_network.py) 和 [Anima 入口](https://github.com/kohya-ss/sd-scripts/blob/690ea7f96c23182352ec63def76d431c6120bd2f/anima_train_network.py) 分支执行；其余三个 Flow 入口的无效字段保留在完整目录、从产品视图隐藏。

与升级前 catalog 逐项比较，全部已有 `effectiveDefault` 保持不变。基础视图字段数：SD 24→24、SDXL 25→26、SD3 26→22、FLUX/Chroma 各 31→26、Lumina 30→24、HunyuanImage 33→28、Anima 28→25；这些统计不包含独立的数据集和采样表单。

在现有 Python 3.10、PyTorch 2.4.1+cu121、transformers 4.54.1、diffusers 0.32.1 环境中完成：

- 工作台后端 198 项测试完成，196 通过，2 项因 Windows 符号链接权限跳过；前端 8 项测试、类型检查及生产构建通过。
- 8 个训练器的真实导入与生成 TOML 读取通过，包含 Anima 新编译参数；32 个采样器与预测类型组合通过构造、设置时间步检查。
- 旧 transformers 的真实 CLIP 兼容路径通过 CPU 微型随机模型前向及权重命名检查。额外执行上游 8 个 CLIP 测试函数，6 通过、2 失败：测试强行包装旧版内部类，缺少 `return_dict` / `.dtype`；旧版实际路径不启用此包装，未复现产品回归。该结果不代表新版 transformers 5.x 已验证。

**未加载实际训练模型或进行 GPU 训练**，上述检查不证明所有精度、量化、显存组合或训练质量已经验证。

根 `requirements.txt` 保持不变。[上游 v0.12.0 说明](https://github.com/kohya-ss/sd-scripts/blob/690ea7f96c23182352ec63def76d431c6120bd2f/README.md) 明确旧依赖仍可使用；其中新版 `diffusers 0.40` 要求 `torch >= 2.6`，不能只单独升级 diffusers 后假设环境兼容。本次参数分级不承担依赖栈迁移。
