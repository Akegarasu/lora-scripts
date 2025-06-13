(function () {
    const SAMPLE_PROMPTS_DEFAULT = "(masterpiece, best quality:1.2), 1girl, solo, --n lowres, bad anatomy, bad hands, text, error, missing fingers, extra digit, fewer digits, cropped, worst quality, low quality, normal quality, jpeg artifacts,signature, watermark, username, blurry,  --w 512  --h 768  --l 7  --s 24  --d 1337"
    const SAMPLE_PROMPTS_DESCRIPTION = "预览图生成参数。可填写直接填写参数，或单独写入txt文件填写路径<br>`--n` 后方为反向提示词<br>`--w`宽，`--h`高<br>`--l`: CFG Scale<br>`--s`: 迭代步数<br>`--d`: 种子"

    let data = {
        RAW: {
            DATASET_SETTINGS: {
                train_data_dir: Schema.string().role('filepicker', { type: "folder", internal: "train-dir" }).default("./train/aki").description("训练数据集路径"),
                reg_data_dir: Schema.string().role('filepicker', { type: "folder", internal: "train-dir" }).description("正则化数据集路径。默认留空，不使用正则化图像"),
                prior_loss_weight: Schema.number().step(0.1).default(1.0).description("正则化 - 先验损失权重"),
                resolution: Schema.string().default("512,512").description("训练图片分辨率，宽x高。支持非正方形，但必须是 64 倍数。"),
                enable_bucket: Schema.boolean().default(true).description("启用 arb 桶以允许非固定宽高比的图片"),
                min_bucket_reso: Schema.number().default(256).description("arb 桶最小分辨率"),
                max_bucket_reso: Schema.number().default(1024).description("arb 桶最大分辨率"),
                bucket_reso_steps: Schema.number().default(64).description("arb 桶分辨率划分单位，SDXL 可以使用 32 (SDXL低于32时失效)"),
                bucket_no_upscale: Schema.boolean().default(true).description("arb 桶不放大图片"),
            },
            CAPTION_SETTINGS: {
                caption_extension: Schema.string().default(".txt").description("Tag 文件扩展名"),
                shuffle_caption: Schema.boolean().default(false).description("训练时随机打乱 tokens"),
                weighted_captions: Schema.boolean().description("使用带权重的 token，不推荐与 shuffle_caption 一同开启"),
                keep_tokens: Schema.number().min(0).max(255).step(1).default(0).description("在随机打乱 tokens 时，保留前 N 个不变"),
                keep_tokens_separator: Schema.string().description("保留 tokens 时使用的分隔符"),
                max_token_length: Schema.number().default(255).description("最大 token 长度"),
                caption_dropout_rate: Schema.number().min(0).step(0.01).description("丢弃全部标签的概率，对一个图片概率不使用 caption 或 class token"),
                caption_dropout_every_n_epochs: Schema.number().min(0).max(100).step(1).description("每 N 个 epoch 丢弃全部标签"),
                caption_tag_dropout_rate: Schema.number().min(0).step(0.01).description("按逗号分隔的标签来随机丢弃 tag 的概率"),
            },
            PRECISION_CACHE_BATCH: {
                mixed_precision: Schema.union(["no", "fp16", "bf16"]).default("bf16").description("训练混合精度, RTX30系列以后也可以指定`bf16`"),
                full_fp16: Schema.boolean().description("完全使用 FP16 精度"),
                full_bf16: Schema.boolean().description("完全使用 BF16 精度"),
                no_half_vae: Schema.boolean().description("不使用半精度 VAE"),
                xformers: Schema.boolean().default(true).description("启用 xformers"),
                sdpa: Schema.boolean().description("启用 sdpa"),
                lowram: Schema.boolean().default(false).description("低内存模式 该模式下会将 U-net、文本编码器、VAE 直接加载到显存中"),
                cache_latents: Schema.boolean().default(true).description("缓存图像 latent, 缓存 VAE 输出以减少 VRAM 使用"),
                cache_latents_to_disk: Schema.boolean().default(true).description("缓存图像 latent 到磁盘"),
                cache_text_encoder_outputs: Schema.boolean().description("缓存文本编码器的输出，减少显存使用。使用时需要关闭 shuffle_caption"),
                cache_text_encoder_outputs_to_disk: Schema.boolean().description("缓存文本编码器的输出到磁盘"),
                persistent_data_loader_workers: Schema.boolean().default(true).description("保留加载训练集的worker，减少每个 epoch 之间的停顿。"),
                vae_batch_size: Schema.number().min(1).description("vae 编码批量大小"),
            }
        },

        LYCORIS_MAIN: Schema.union([
            Schema.object({
                network_module: Schema.const('lycoris.kohya').required(),
                lycoris_algo: Schema.union(["locon", "loha", "lokr", "ia3", "dylora", "glora", "diag-oft", "boft"]).default("locon").description('LyCORIS 网络算法'),
                conv_dim: Schema.number().default(4),
                conv_alpha: Schema.number().default(1),
                dropout: Schema.number().step(0.01).default(0).description('dropout 概率。推荐 0~0.5，LoHa/LoKr/(IA)^3暂不支持'),
                train_norm: Schema.boolean().default(false).description('训练 Norm 层，不支持 (IA)^3'),
            }),
            Schema.object({}),
        ]),

        LYCORIS_LOKR: Schema.union([
            Schema.object({
                lycoris_algo: Schema.const('lokr').required(),
                lokr_factor: Schema.number().min(-1).default(-1).description('常用 `4~无穷`（填写 -1 为无穷）'),
            }),
            Schema.object({}),
        ]),

        NETWORK_OPTION_DYLORA: Schema.union([
            Schema.object({
                network_module: Schema.const('networks.dylora').required(),
                dylora_unit: Schema.number().min(1).default(4).description(' dylora 分割块数单位，最小 1 也最慢。一般 4、8、12、16 这几个选'),
            }),
            Schema.object({}),
        ]),

        NETWORK_OPTION_BASEWEIGHT: Schema.union([
            Schema.object({
                enable_base_weight: Schema.const(true).required(),
                base_weights: Schema.string().role('textarea').description("合并入底模的 LoRA 路径，一行一个路径"),
                base_weights_multiplier: Schema.string().role('textarea').description("合并入底模的 LoRA 权重，一行一个数字"),
            }),
            Schema.object({}),
        ]),

        NETWORK_OPTION_BLOCK_WEIGHTS: Schema.union([
            Schema.object({
                enable_block_weights: Schema.const(true).required(),
                down_lr_weight: Schema.string().role('folder').default("1,1,1,1,1,1,1,1,1,1,1,1").description("U-Net 的 Encoder 层分层学习率权重，共 12 层"),
                mid_lr_weight: Schema.string().role('folder').default("1").description("U-Net 的 Mid 层分层学习率权重，共 1 层"),
                up_lr_weight: Schema.string().role('folder').default("1,1,1,1,1,1,1,1,1,1,1,1").description("U-Net 的 Decoder 层分层学习率权重，共 12 层"),
                block_lr_zero_threshold: Schema.number().step(0.01).default(0).description("分层学习率置 0 阈值"),
            }),
            Schema.object({}),
        ]),

        SAVE_SETTINGS: Schema.intersect([
            Schema.object({
                output_name: Schema.string().default("aki").description("模型保存名称"),
                output_dir: Schema.string().role('filepicker', { type: "folder" }).default("./output").description("模型保存文件夹"),
                save_model_as: Schema.union(["safetensors", "pt", "ckpt"]).default("safetensors").description("模型保存格式"),
                save_precision: Schema.union(["fp16", "float", "bf16"]).default("fp16").description("模型保存精度"),
                save_every_n_epochs: Schema.number().default(2).description("每 N epoch（轮）自动保存一次模型"),
                save_state: Schema.boolean().default(false).description("保存训练状态 配合 `resume` 参数可以继续从某个状态训练"),
            }).description("保存设置"),
            Schema.union([
                Schema.object({
                    save_state: Schema.const(true).required(),
                    save_last_n_epochs_state: Schema.number().min(1).description("仅保存最后 n epoch 的训练状态"),
                }),
                Schema.object({})
            ])
        ]),

        LR_OPTIMIZER: Schema.intersect([
            Schema.object({
                learning_rate: Schema.string().default("1e-4").description("总学习率, 在分开设置 U-Net 与文本编码器学习率后这个值失效。"),
                unet_lr: Schema.string().default("1e-4").description("U-Net 学习率"),
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
                loss_type: Schema.union(["l1", "l2", "huber", "smooth_l1"]).description("损失函数类型"),
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
                    "RAdamScheduleFree",
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
                    "Prodigy",
                    "prodigyplus.ProdigyPlusScheduleFree",
                    "pytorch_optimizer.CAME"
                ]).default("AdamW8bit").description("优化器设置"),
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
            enable_contrastive: Schema.boolean()
            .default(false)
            .description('启用对比学习模块'),
        
          negative_sampling_method: Schema.union([
            'Random-Noise','Permutation','Random-index','Circular','Hard-Negative',
          ])
            .default('Random-Noise')
            .description('选择负样本生成策略')
            .onlyWhen('enable_contrastive', Schema.const(true)),
        
          noise_strength: Schema.number()
            .min(0)
            .max(10)
            .default(1.0)
            .description('噪音强度参数')
            .onlyWhen('enable_contrastive', Schema.const(true)),
        
          contrastive_weight: Schema.number()
            .min(0)
            .max(1)
            .default(0.05)
            .description('对比损失权重')
            .onlyWhen('enable_contrastive', Schema.const(true)),
        
          contrastive_warmup_steps: Schema.number()
            .default(100)
            .description('使用随机负样本的步数')
            .onlyWhen('enable_contrastive', Schema.const(true)),
        ]),

        PREVIEW_IMAGE: Schema.intersect([
            Schema.object({
                enable_preview: Schema.boolean().default(false).description('启用训练预览图'),
            }).description('训练预览图设置'),

            Schema.union([
                Schema.object({
                    enable_preview: Schema.const(true).required(),
                    randomly_choice_prompt: Schema.boolean().default(false).description('随机选择预览图 Prompt'),
                    prompt_file: Schema.string().role('textarea').description('预览图 Prompt 文件路径。填写后将采用文件内的 prompt，而下方的选项将失效。'),
                    positive_prompts: Schema.string().role('textarea').default('masterpiece, best quality, 1girl, solo').description("Prompt"),
                    negative_prompts: Schema.string().role('textarea').default('lowres, bad anatomy, bad hands, text, error, missing fingers, extra digit, fewer digits, cropped, worst quality, low quality, normal quality, jpeg artifacts,signature, watermark, username, blurry').description("Negative Prompt"),
                    sample_width: Schema.number().default(512).description('预览图宽'),
                    sample_height: Schema.number().default(512).description('预览图高'),
                    sample_cfg: Schema.number().min(1).max(30).default(7).description('CFG Scale'),
                    sample_seed: Schema.number().default(2333).description('种子'),
                    sample_steps: Schema.number().min(1).max(300).default(24).description('迭代步数'),
                    sample_sampler: Schema.union(["ddim", "pndm", "lms", "euler", "euler_a", "heun", "dpm_2", "dpm_2_a", "dpmsolver", "dpmsolver++", "dpmsingle", "k_lms", "k_euler", "k_euler_a", "k_dpm_2", "k_dpm_2_a"]).default("euler_a").description("生成预览图所用采样器"),
                    sample_every_n_epochs: Schema.number().default(2).description("每 N 个 epoch 生成一次预览图"),
                }),
                Schema.object({}),
            ]),
        ]),

        LOG_SETTINGS: Schema.intersect([
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

        NOISE_SETTINGS: Schema.object({
            noise_offset: Schema.number().step(0.01).description("在训练中添加噪声偏移来改良生成非常暗或者非常亮的图像，如果启用推荐为 0.1"),
            multires_noise_iterations: Schema.number().step(1).description("多分辨率（金字塔）噪声迭代次数 推荐 6-10。无法与 noise_offset 一同启用"),
            multires_noise_discount: Schema.number().step(0.01).description("多分辨率（金字塔）衰减率 推荐 0.3-0.8，须同时与上方参数 multires_noise_iterations 一同启用"),
        }).description("噪声设置"),

        DATA_ENCHANCEMENT: Schema.object({
            color_aug: Schema.boolean().description("颜色改变"),
            flip_aug: Schema.boolean().description("图像翻转"),
            random_crop: Schema.boolean().description("随机剪裁"),
        }).description("数据增强"),

        OTHER: Schema.object({
            seed: Schema.number().default(1337).description("随机种子"),
            clip_skip: Schema.number().role("slider").min(0).max(12).step(1).default(2).description("CLIP 跳过层数 *玄学*"),
            ui_custom_params: Schema.string().role('textarea').description("**危险** 自定义参数，请输入 TOML 格式，将会直接覆盖当前界面内任何参数。实时更新，推荐写完后再粘贴过来"),
        }).description("其他设置"),

        DISTRIBUTED_TRAINING: Schema.object({
            ddp_timeout: Schema.number().min(0).description("分布式训练超时时间"),
            ddp_gradient_as_bucket_view: Schema.boolean(),
        }).description("分布式训练"),

    }

    return data
})()
