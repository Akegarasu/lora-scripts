Schema.intersect([
    Schema.intersect([
        Schema.object({
            model_train_type: Schema.string().default("flux-lora").disabled().description("训练种类"),
            pretrained_model_name_or_path: Schema.string().role('filepicker').default("./sd-models/model.safetensors").description("Flux 模型路径"),
            ae: Schema.string().role('filepicker').description("AE 模型文件路径"),
            clip_l: Schema.string().role('filepicker').description("clip_l 模型文件路径"),
            t5xxl: Schema.string().role('filepicker').description("t5xxl 模型文件路径"),
            resume: Schema.string().role('filepicker').description("从某个 `save_state` 保存的中断状态继续训练，填写文件路径"),
        }).description("训练用模型"),
    ]),

    Schema.object({
        timestep_sampling: Schema.union(["sigma", "uniform", "sigmoid", "shift"]).default("sigmoid").description("时间步采样"),
        sigmoid_scale: Schema.number().step(0.001).default(1.0).description("sigmoid 缩放"),
        model_prediction_type: Schema.union(["raw", "additive", "sigma_scaled"]).default("raw").description("模型预测类型"),
        discrete_flow_shift: Schema.number().step(0.001).default(1.0).description("Euler 调度器离散流位移"),
        loss_type: Schema.union(["l1", "l2", "huber", "smooth_l1"]).default("l2").description("损失函数类型"),
        guidance_scale: Schema.number().step(0.01).default(1.0).description("CFG 引导缩放"),
    }).description("Flux 专用参数"),

    Schema.object({
        train_data_dir: Schema.string().role('filepicker', { type: "folder" }).default("./train/aki").description("训练数据集路径"),
        reg_data_dir: Schema.string().role('filepicker', { type: "folder" }).description("正则化数据集路径。默认留空，不使用正则化图像"),
        prior_loss_weight: Schema.number().step(0.1).default(1.0).description("正则化 - 先验损失权重"),
        resolution: Schema.string().default("768,768").description("训练图片分辨率，宽x高。支持非正方形，但必须是 64 倍数。"),
        enable_bucket: Schema.boolean().default(true).description("启用 arb 桶以允许非固定宽高比的图片"),
        min_bucket_reso: Schema.number().default(256).description("arb 桶最小分辨率"),
        max_bucket_reso: Schema.number().default(2048).description("arb 桶最大分辨率"),
        bucket_reso_steps: Schema.number().default(32).description("arb 桶分辨率划分单位，SDXL 可以使用 32 (SDXL低于32时失效)"),
        bucket_no_upscale: Schema.boolean().default(true).description("arb 桶不放大图片"),
    }).description("数据集设置"),

    Schema.object({
        output_name: Schema.string().default("aki").description("模型保存名称"),
        output_dir: Schema.string().role('filepicker', { type: "folder" }).default("./output").description("模型保存文件夹"),
        save_model_as: Schema.union(["safetensors", "pt", "ckpt"]).default("safetensors").description("模型保存格式"),
        save_precision: Schema.union(["fp16", "float", "bf16"]).default("bf16").description("模型保存精度"),
        save_every_n_epochs: Schema.number().default(2).description("每 N epoch（轮）自动保存一次模型"),
        save_state: Schema.boolean().description("保存训练状态 配合 `resume` 参数可以继续从某个状态训练"),
    }).description("保存设置"),

    Schema.object({
        max_train_epochs: Schema.number().min(1).default(20).description("最大训练 epoch（轮数）"),
        train_batch_size: Schema.number().min(1).default(1).description("批量大小, 越高显存占用越高"),
        gradient_checkpointing: Schema.boolean().default(true).description("梯度检查点"),
        gradient_accumulation_steps: Schema.number().min(1).default(1).description("梯度累加步数"),
        network_train_unet_only: Schema.boolean().default(true).description("仅训练 U-Net"),
        network_train_text_encoder_only: Schema.boolean().default(false).description("仅训练文本编码器"),
    }).description("训练相关参数"),

    Schema.intersect([
        Schema.object({
            learning_rate: Schema.string().default("1e-4").description("总学习率, 在分开设置 U-Net 与文本编码器学习率后这个值失效。"),
            unet_lr: Schema.string().default("5e-4").description("U-Net 学习率"),
            text_encoder_lr: Schema.string().default("1e-5").description("文本编码器学习率"),
            lr_scheduler: Schema.union([
                "linear",
                "cosine",
                "cosine_with_restarts",
                "polynomial",
                "constant",
                "constant_with_warmup",
            ]).default("cosine_with_restarts").description("学习率调度器设置"),
            lr_warmup_steps: Schema.number().default(0).description('学习率预热步数'),
        }).description("学习率与优化器设置"),

        Schema.union([
            Schema.object({
                lr_scheduler: Schema.const('cosine_with_restarts'),
                lr_scheduler_num_cycles: Schema.number().default(1).description('重启次数'),
            }),
            Schema.object({}),
        ]),

        Schema.object({
            optimizer_type: Schema.union([
                "AdamW",
                "AdamW8bit",
                "PagedAdamW8bit",
                "Lion",
                "Lion8bit",
                "PagedLion8bit",
                "SGDNesterov",
                "SGDNesterov8bit",
                "DAdaptation",
                "DAdaptAdam",
                "DAdaptAdaGrad",
                "DAdaptAdanIP",
                "DAdaptLion",
                "DAdaptSGD",
                "AdaFactor",
                "Prodigy"
            ]).default("PagedAdamW8bit").description("优化器设置"),
            min_snr_gamma: Schema.number().step(0.1).description("最小信噪比伽马值, 如果启用推荐为 5"),
        }),

        Schema.union([
            Schema.object({
                optimizer_type: Schema.const('Prodigy').required(),
                prodigy_d0: Schema.string(),
                prodigy_d_coef: Schema.string().default("2.0"),
            }),
            Schema.object({}),
        ]),

        Schema.object({
            optimizer_args_custom: Schema.array(String).role('table').description('自定义 optimizer_args，一行一个'),
        })
    ]),

    Schema.intersect([
        Schema.object({
            network_module: Schema.union(["networks.lora_flux"]).default("networks.lora_flux").description("训练网络模块"),
            network_weights: Schema.string().role('filepicker').description("从已有的 LoRA 模型上继续训练，填写路径"),
            network_dim: Schema.number().min(1).default(2).description("网络维度，常用 4~128，不是越大越好, 低dim可以降低显存占用"),
            network_alpha: Schema.number().min(1).default(16).description("常用值：等于 network_dim 或 network_dim*1/2 或 1。使用较小的 alpha 需要提升学习率"),
            network_dropout: Schema.number().step(0.01).default(0).description('dropout 概率 （与 lycoris 不兼容，需要用 lycoris 自带的）'),
            scale_weight_norms: Schema.number().step(0.01).min(0).description("最大范数正则化。如果使用，推荐为 1"),
            network_args_custom: Schema.array(String).role('table').description('自定义 network_args，一行一个'),
            enable_base_weight: Schema.boolean().default(false).description('启用基础权重（差异炼丹）'),
        }).description("网络设置"),

        Schema.union([
            Schema.object({
                enable_base_weight: Schema.const(true).required(),
                base_weights: Schema.string().role('textarea').description("合并入底模的 LoRA 路径，一行一个路径"),
                base_weights_multiplier: Schema.string().role('textarea').description("合并入底模的 LoRA 权重，一行一个数字"),
            }),
            Schema.object({}),
        ]),
    ]),

    Schema.intersect([
        Schema.object({
            enable_preview: Schema.boolean().default(false).description('启用训练预览图'),
        }).description('训练预览图设置'),

        Schema.union([
            Schema.object({
                enable_preview: Schema.const(true).required(),
                sample_prompts: Schema.string().role('textarea').default(window.__MIKAZUKI__.SAMPLE_PROMPTS_DEFAULT).description(window.__MIKAZUKI__.SAMPLE_PROMPTS_DESCRIPTION),
                sample_sampler: Schema.union(["ddim", "pndm", "lms", "euler", "euler_a", "heun", "dpm_2", "dpm_2_a", "dpmsolver", "dpmsolver++", "dpmsingle", "k_lms", "k_euler", "k_euler_a", "k_dpm_2", "k_dpm_2_a"]).default("euler_a").description("生成预览图所用采样器"),
                sample_every_n_epochs: Schema.number().default(2).description("每 N 个 epoch 生成一次预览图"),
            }),
            Schema.object({}),
        ]),
    ]),

    Schema.intersect([
        Schema.object({
            log_with: Schema.union(["tensorboard", "wandb"]).default("tensorboard").description("日志模块"),
            log_prefix: Schema.string().description("日志前缀"),
            log_tracker_name: Schema.string().description("日志追踪器名称"),
            logging_dir: Schema.string().default("./logs").description("日志保存文件夹"),
        }).description('日志设置'),

        Schema.union([
            Schema.object({
                log_with: Schema.const("wandb").required(),
                wandb_api_key: Schema.string().required().description("wandb 的 api 密钥"),
            }),
            Schema.object({}),
        ]),
    ]),

    Schema.object({
        caption_extension: Schema.string().default(".txt").description("Tag 文件扩展名"),
        shuffle_caption: Schema.boolean().default(false).description("训练时随机打乱 tokens"),
        weighted_captions: Schema.boolean().description("使用带权重的 token，不推荐与 shuffle_caption 一同开启"),
        keep_tokens: Schema.number().min(0).max(255).step(1).default(0).description("在随机打乱 tokens 时，保留前 N 个不变"),
        keep_tokens_separator: Schema.string().description("保留 tokens 时使用的分隔符"),
        max_token_length: Schema.number().default(255).description("最大 token 长度"),
        caption_dropout_rate: Schema.number().min(0).step(0.01).description("丢弃全部标签的概率，对一个图片概率不使用 caption 或 class token"),
        caption_dropout_every_n_epochs: Schema.number().min(0).max(100).step(1).description("每 N 个 epoch 丢弃全部标签"),
        caption_tag_dropout_rate: Schema.number().min(0).step(0.01).description("按逗号分隔的标签来随机丢弃 tag 的概率"),
    }).description("caption（Tag）选项"),

    Schema.object({
        color_aug: Schema.boolean().description("颜色改变"),
        flip_aug: Schema.boolean().description("图像翻转"),
        random_crop: Schema.boolean().description("随机剪裁"),
    }).description("数据增强"),

    Schema.object({
        seed: Schema.number().default(1337).description("随机种子"),
        clip_skip: Schema.number().role("slider").min(0).max(12).step(1).default(2).description("CLIP 跳过层数 *玄学*"),
        ui_custom_params: Schema.string().role('textarea').description("**危险** 自定义参数，请输入 TOML 格式，将会直接覆盖当前界面内任何参数。实时更新，推荐写完后再粘贴过来"),
    }).description("高级设置"),

    Schema.object({
        mixed_precision: Schema.union(["no", "fp16", "bf16"]).default("bf16").description("训练混合精度, RTX30系列以后也可以指定`bf16`"),
        full_fp16: Schema.boolean().description("完全使用 FP16 精度"),
        full_bf16: Schema.boolean().description("完全使用 BF16 精度"),
        fp8_base: Schema.boolean().default(true).description("对基础模型使用 FP8 精度"),
        fp8_base_unet: Schema.boolean().description("仅对 U-Net 使用 FP8 精度（CLIP-L不使用）"),
        no_half_vae: Schema.boolean().description("不使用半精度 VAE"),
        sdpa: Schema.boolean().default(true).description("启用 sdpa"),
        lowram: Schema.boolean().default(false).description("低内存模式 该模式下会将 U-net、文本编码器、VAE 直接加载到显存中"),
        cache_latents: Schema.boolean().default(true).description("缓存图像 latent, 缓存 VAE 输出以减少 VRAM 使用"),
        cache_latents_to_disk: Schema.boolean().default(true).description("缓存图像 latent 到磁盘"),
        cache_text_encoder_outputs: Schema.boolean().default(true).description("缓存文本编码器的输出，减少显存使用。使用时需要关闭 shuffle_caption"),
        cache_text_encoder_outputs_to_disk: Schema.boolean().default(true).description("缓存文本编码器的输出到磁盘"),
        persistent_data_loader_workers: Schema.boolean().default(true).description("保留加载训练集的worker，减少每个 epoch 之间的停顿。"),
        vae_batch_size: Schema.number().min(1).description("vae 编码批量大小"),
    }).description("速度优化选项"),

    Schema.object({
        ddp_timeout: Schema.number().min(0).description("分布式训练超时时间"),
        ddp_gradient_as_bucket_view: Schema.boolean(),
    }).description("分布式训练"),
]);
