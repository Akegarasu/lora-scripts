# LoRA train script by @Akegarasu

# Train data path | 设置训练用模型、图片
$pretrained_model = "./sd-models/model.ckpt" # base model path | 底模路径
$train_data_dir = "./train/aki" # train dataset path | 训练数据集路径
$reg_data_dir = "" # directory for regularization images | 正则化数据集路径，默认不使用正则化图像。

# Network settings | 网络设置
$network_module = "networks.lora" # 在这里将会设置训练的网络种类，默认为 networks.lora 也就是 LoRA 训练。如果你想训练 LyCORIS（LoCon、LoHa） 等，则修改这个值为 lycoris.kohya
$network_weights = "" # pretrained weights for LoRA network | 若需要从已有的 LoRA 模型上继续训练，请填写 LoRA 模型路径。
$network_dim = 32 # network dim | 常用 4~128，不是越大越好
$network_alpha = 32 # network alpha | 常用与 network_dim 相同的值或者采用较小的值，如 network_dim的一半 防止下溢。默认值为 1，使用较小的 alpha 需要提升学习率。

# Train related params | 训练相关参数
$resolution = "512,512" # image resolution w,h. 图片分辨率，宽,高。支持非正方形，但必须是 64 倍数。
$batch_size = 1 # batch size
$max_train_epoches = 10 # max train epoches | 最大训练 epoch
$save_every_n_epochs = 2 # save every n epochs | 每 N 个 epoch 保存一次

$train_unet_only = 0 # train U-Net only | 仅训练 U-Net，开启这个会牺牲效果大幅减少显存使用。6G显存可以开启
$train_text_encoder_only = 0 # train Text Encoder only | 仅训练 文本编码器

$noise_offset = 0 # noise offset | 在训练中添加噪声偏移来改良生成非常暗或者非常亮的图像，如果启用，推荐参数为 0.1
$keep_tokens = 0 # keep heading N tokens when shuffling caption tokens | 在随机打乱 tokens 时，保留前 N 个不变。

# Learning rate | 学习率
$lr = "1e-4"
$unet_lr = "1e-4"
$text_encoder_lr = "1e-5"
$lr_scheduler = "cosine_with_restarts" # "linear", "cosine", "cosine_with_restarts", "polynomial", "constant", "constant_with_warmup"
$lr_warmup_steps = 0 # warmup steps | 仅在 lr_scheduler 为 constant_with_warmup 时需要填写这个值
$lr_restart_cycles = 1 # cosine_with_restarts restart cycles | 余弦退火重启次数，仅在 lr_scheduler 为 cosine_with_restarts 时起效。

# Output settings | 输出设置
$output_name = "aki" # output model name | 模型保存名称
$save_model_as = "safetensors" # model save ext | 模型保存格式 ckpt, pt, safetensors

# 其他设置
$min_bucket_reso = 256 # arb min resolution | arb 最小分辨率
$max_bucket_reso = 1024 # arb max resolution | arb 最大分辨率
$persistent_data_loader_workers = 0 # persistent dataloader workers | 容易爆内存，保留加载训练集的worker，减少每个 epoch 之间的停顿
$clip_skip = 2 # clip skip | 玄学 一般用 2

# 优化器设置
$use_8bit_adam = 1 # use 8bit adam optimizer | 使用 8bit adam 优化器节省显存，默认启用。部分 10 系老显卡无法使用，修改为 0 禁用。
$use_lion = 0 # use lion optimizer | 使用 Lion 优化器

# LyCORIS 训练设置
$algo = "lora" # LyCORIS network algo | LyCORIS 网络算法 可选 lora、loha。lora即为locon
$conv_dim = 4 # conv dim | 类似于 network_dim，推荐为 4
$conv_alpha = 4 # conv alpha | 类似于 network_alpha，可以采用与 conv_dim 一致或者更小的值

# ============= DO NOT MODIFY CONTENTS BELOW | 请勿修改下方内容 =====================
# Activate python venv
.\venv\Scripts\activate

$Env:HF_HOME = "huggingface"
$ext_args = [System.Collections.ArrayList]::new()

if ($train_unet_only) {
  [void]$ext_args.Add("--network_train_unet_only")
}

if ($train_text_encoder_only) {
  [void]$ext_args.Add("--network_train_text_encoder_only")
}

if ($network_weights) {
  [void]$ext_args.Add("--network_weights=" + $network_weights)
}

if ($reg_data_dir) {
  [void]$ext_args.Add("--reg_data_dir=" + $reg_data_dir)
}

if ($use_8bit_adam) {
  [void]$ext_args.Add("--use_8bit_adam")
}

if ($use_lion) {
  [void]$ext_args.Add("--use_lion_optimizer")
}

if ($persistent_data_loader_workers) {
  [void]$ext_args.Add("--persistent_data_loader_workers")
}

if ($network_module -eq "lycoris.kohya") {
  [void]$ext_args.Add("--network_args")
  [void]$ext_args.Add("conv_dim=$conv_dim")
  [void]$ext_args.Add("conv_alpha=$conv_alpha")
  [void]$ext_args.Add("algo=$algo")
}

if ($noise_offset) {
  [void]$ext_args.Add("--noise_offset=$noise_offset")
}

# run train
accelerate launch --num_cpu_threads_per_process=8 "./sd-scripts/train_network.py" `
  --enable_bucket `
  --pretrained_model_name_or_path=$pretrained_model `
  --train_data_dir=$train_data_dir `
  --output_dir="./output" `
  --logging_dir="./logs" `
  --log_prefix=$output_name `
  --resolution=$resolution `
  --network_module=$network_module `
  --max_train_epochs=$max_train_epoches `
  --learning_rate=$lr `
  --unet_lr=$unet_lr `
  --text_encoder_lr=$text_encoder_lr `
  --lr_scheduler=$lr_scheduler `
  --lr_warmup_steps=$lr_warmup_steps `
  --lr_scheduler_num_cycles=$lr_restart_cycles `
  --network_dim=$network_dim `
  --network_alpha=$network_alpha `
  --output_name=$output_name `
  --train_batch_size=$batch_size `
  --save_every_n_epochs=$save_every_n_epochs `
  --mixed_precision="fp16" `
  --save_precision="fp16" `
  --seed="1337" `
  --cache_latents `
  --clip_skip=$clip_skip `
  --prior_loss_weight=1 `
  --max_token_length=225 `
  --caption_extension=".txt" `
  --save_model_as=$save_model_as `
  --min_bucket_reso=$min_bucket_reso `
  --max_bucket_reso=$max_bucket_reso `
  --keep_tokens=$keep_tokens `
  --xformers --shuffle_caption $ext_args
Write-Output "Train finished"
Read-Host | Out-Null ;