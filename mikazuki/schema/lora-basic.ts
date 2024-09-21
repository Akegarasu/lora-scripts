Schema.intersect([
    Schema.object({
        pretrained_model_name_or_path: Schema.string().role('filepicker', {type: "model-file"}).default("./sd-models/model.safetensors").description("底模文件路径"),
    }).description("训练用模型"),

    Schema.object({
        train_data_dir: Schema.string().role('filepicker', { type: "folder", internal: "train-dir" }).default("./train/aki").description("训练数据集路径"),
        reg_data_dir: Schema.string().role('filepicker', { type: "folder", internal: "train-dir" }).description("正则化数据集路径。默认留空，不使用正则化图像"),
        resolution: Schema.string().default("512,512").description("训练图片分辨率，宽x高。支持非正方形，但必须是 64 倍数。"),
    }).description("数据集设置"),

    Schema.object({
        output_name: Schema.string().default("aki").description("模型保存名称"),
        output_dir: Schema.string().default("./output").role('filepicker', { type: "folder" }).description("模型保存文件夹"),
        save_every_n_epochs: Schema.number().default(2).description("每 N epoch（轮）自动保存一次模型"),
    }).description("保存设置"),

    Schema.object({
        max_train_epochs: Schema.number().min(1).default(10).description("最大训练 epoch（轮数）"),
        train_batch_size: Schema.number().min(1).default(1).description("批量大小"),
    }).description("训练相关参数"),

    Schema.intersect([
        Schema.object({
            unet_lr: Schema.string().default("1e-4").description("U-Net 学习率"),
            text_encoder_lr: Schema.string().default("1e-5").description("文本编码器学习率"),
            lr_scheduler: Schema.union([
                "cosine",
                "cosine_with_restarts",
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
                "AdamW8bit",
                "Lion",
            ]).default("AdamW8bit").description("优化器设置"),
        })
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
            network_weights: Schema.string().role('filepicker', { type: "model-file", internal: "model-saved-file" }).description("从已有的 LoRA 模型上继续训练，填写路径"),
            network_dim: Schema.number().min(8).max(256).step(8).default(32).description("网络维度，常用 4~128，不是越大越好, 低dim可以降低显存占用"),
            network_alpha: Schema.number().min(1).default(32).description(
                "常用值：等于 network_dim 或 network_dim*1/2 或 1。使用较小的 alpha 需要提升学习率。"
            ),
        }).description("网络设置"),
    ]),

    Schema.object({
        shuffle_caption: Schema.boolean().default(true).description("训练时随机打乱 tokens"),
        keep_tokens: Schema.number().min(0).max(255).step(1).default(0).description("在随机打乱 tokens 时，保留前 N 个不变"),
    }).description("caption 选项"),

    Schema.object({
        mixed_precision: Schema.union(["no", "fp16", "bf16"]).default("fp16").description("混合精度, RTX30系列以后也可以指定`bf16`"),
        no_half_vae: Schema.boolean().description("不使用半精度 VAE，当出现 NaN detected in latents 报错时使用"),
        xformers: Schema.boolean().default(true).description("启用 xformers"),
        cache_latents: Schema.boolean().default(true).description("缓存图像 latent, 缓存 VAE 输出以减少 VRAM 使用")
    }).description("速度优化选项"),
]);
