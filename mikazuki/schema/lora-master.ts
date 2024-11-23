Schema.intersect([
    Schema.intersect([
        Schema.object({
            model_train_type: Schema.union(["sd-lora", "sdxl-lora"]).default("sd-lora").description("训练种类"),
            pretrained_model_name_or_path: Schema.string().role('filepicker', { type: "model-file" }).default("./sd-models/model.safetensors").description("底模文件路径"),
            resume: Schema.string().role('filepicker', { type: "folder" }).description("从某个 `save_state` 保存的中断状态继续训练，填写文件路径"),
            vae: Schema.string().role('filepicker', { type: "model-file" }).description("(可选) VAE 模型文件路径，使用外置 VAE 文件覆盖模型内本身的"),
        }).description("训练用模型"),

        Schema.union([
            Schema.object({
                model_train_type: Schema.const("sd-lora"),
                v2: Schema.boolean().default(false).description("底模为 sd2.0 以后的版本需要启用"),
            }),
            Schema.object({}),
        ]),

        Schema.union([
            Schema.object({
                model_train_type: Schema.const("sd-lora"),
                v2: Schema.const(true).required(),
                v_parameterization: Schema.boolean().default(false).description("v-parameterization 学习"),
                scale_v_pred_loss_like_noise_pred: Schema.boolean().default(false).description("缩放 v-prediction 损失（与v-parameterization配合使用）"),
            }),
            Schema.object({}),
        ]),
    ]),

    // 数据集设置
    Schema.object(SHARED_SCHEMAS.RAW.DATASET_SETTINGS).description("数据集设置"),

    // 保存设置
    SHARED_SCHEMAS.SAVE_SETTINGS,

    Schema.object({
        max_train_epochs: Schema.number().min(1).default(10).description("最大训练 epoch（轮数）"),
        train_batch_size: Schema.number().min(1).default(1).description("批量大小, 越高显存占用越高"),
        gradient_checkpointing: Schema.boolean().default(false).description("梯度检查点"),
        gradient_accumulation_steps: Schema.number().min(1).description("梯度累加步数"),
        network_train_unet_only: Schema.boolean().default(false).description("仅训练 U-Net 训练SDXL Lora时推荐开启"),
        network_train_text_encoder_only: Schema.boolean().default(false).description("仅训练文本编码器"),
    }).description("训练相关参数"),

    // 学习率&优化器设置
    SHARED_SCHEMAS.LR_OPTIMIZER,

    Schema.intersect([
        Schema.object({
            network_module: Schema.union(["networks.lora", "networks.dylora", "networks.oft", "lycoris.kohya"]).default("networks.lora").description("训练网络模块"),
            network_weights: Schema.string().role('filepicker').description("从已有的 LoRA 模型上继续训练，填写路径"),
            network_dim: Schema.number().min(1).default(32).description("网络维度，常用 4~128，不是越大越好, 低dim可以降低显存占用"),
            network_alpha: Schema.number().min(1).default(32).description("常用值：等于 network_dim 或 network_dim*1/2 或 1。使用较小的 alpha 需要提升学习率"),
            network_dropout: Schema.number().step(0.01).default(0).description('dropout 概率 （与 lycoris 不兼容，需要用 lycoris 自带的）'),
            scale_weight_norms: Schema.number().step(0.01).min(0).description("最大范数正则化。如果使用，推荐为 1"),
            network_args_custom: Schema.array(String).role('table').description('自定义 network_args，一行一个'),
            enable_block_weights: Schema.boolean().default(false).description('启用分层学习率训练（只支持网络模块 networks.lora）'),
            enable_base_weight: Schema.boolean().default(false).description('启用基础权重（差异炼丹）'),
        }).description("网络设置"),

        Schema.union([
            Schema.object({
                network_module: Schema.const('lycoris.kohya').required(),
                lycoris_algo: Schema.union(["locon", "loha", "lokr", "ia3", "dylora", "glora", "diag-oft", "boft"]).default("locon").description('LyCORIS 网络算法'),
                conv_dim: Schema.number().default(4),
                conv_alpha: Schema.number().default(1),
                dropout: Schema.number().step(0.01).default(0).description('dropout 概率。推荐 0~0.5，LoHa/LoKr/(IA)^3暂不支持'),
                train_norm: Schema.boolean().default(false).description('训练 Norm 层，不支持 (IA)^3'),
            }),
            Schema.object({
                network_module: Schema.const('networks.dylora').required(),
                dylora_unit: Schema.number().min(1).default(4).description(' dylora 分割块数单位，最小 1 也最慢。一般 4、8、12、16 这几个选'),
            }),
            Schema.object({}),
        ]),

        Schema.union([
            Schema.object({
                lycoris_algo: Schema.const('lokr').required(),
                lokr_factor: Schema.number().min(-1).default(-1).description('常用 `4~无穷`（填写 -1 为无穷）'),
            }),
            Schema.object({}),
        ]),

        Schema.union([
            Schema.object({
                enable_block_weights: Schema.const(true).required(),
                down_lr_weight: Schema.string().role('folder').default("1,1,1,1,1,1,1,1,1,1,1,1").description("U-Net 的 Encoder 层分层学习率权重，共 12 层"),
                mid_lr_weight: Schema.string().role('folder').default("1").description("U-Net 的 Mid 层分层学习率权重，共 1 层"),
                up_lr_weight: Schema.string().role('folder').default("1,1,1,1,1,1,1,1,1,1,1,1").description("U-Net 的 Decoder 层分层学习率权重，共 12 层"),
                block_lr_zero_threshold: Schema.number().step(0.01).default(0).description("分层学习率置 0 阈值"),
            }),
            Schema.object({}),
        ]),

        Schema.union([
            Schema.object({
                enable_base_weight: Schema.const(true).required(),
                base_weights: Schema.string().role('textarea').description("合并入底模的 LoRA 路径，一行一个路径"),
                base_weights_multiplier: Schema.string().role('textarea').description("合并入底模的 LoRA 权重，一行一个数字"),
            }),
            Schema.object({}),
        ]),
    ]),

    // 预览图设置
    SHARED_SCHEMAS.PREVIEW_IMAGE,

    // 日志设置
    SHARED_SCHEMAS.LOG_SETTINGS,

    // caption 选项
    Schema.object(SHARED_SCHEMAS.RAW.CAPTION_SETTINGS).description("caption（Tag）选项"),

    // 数据增强
    SHARED_SCHEMAS.DATA_ENCHANCEMENT,

    // 其他选项
    SHARED_SCHEMAS.OTHER,

    // 速度优化选项
    SHARED_SCHEMAS.PRECISION_CACHE_BATCH,

    // 分布式训练
    SHARED_SCHEMAS.DISTRIBUTED_TRAINING
]);
