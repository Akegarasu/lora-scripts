# LoRA train script by @Akegarasu

# Train data path | 设置训练用模型、图片
$pretrained_model = "./sd-models/model.ckpt" # base model path | 底模路径
$is_v2_model = 0 # SD2.0 model | SD2.0模型 2.0模型下 clip_skip 默认无效
$parameterization = 0 # parameterization | 参数化 本参数需要和 V2 参数同步使用 实验性功能
$train_data_dir = "./train/aki" # train dataset path | 训练数据集路径
$reg_data_dir = "" # directory for regularization images | 正则化数据集路径，默认不使用正则化图像。

# Train related params | 训练相关参数
$resolution = "512,512" # image resolution w,h. 图片分辨率，宽,高。支持非正方形，但必须是 64 倍数。
$batch_size = 2 # batch size
$max_train_steps = 3000 # max train steps | 最大训练步数 当 epoch 指定时 本参数自动无效
$max_train_epoches = 40 # max train epoches | 最大训练 epoch
$save_every_n_epochs = 10 # save every n epochs | 每 N 个 epoch 保存一次

$network_dim = 64 # network dim | 常用 4~128，不是越大越好
$network_alpha = 64 # network alpha | 常用与 network_dim 相同的值或者采用较小的值，如 network_dim 的一半 防止下溢。默认值为 1，使用较小的 alpha 需要提升学习率。

$train_unet_only = 0 # train U-Net only | 仅训练 U-Net，开启这个会牺牲效果大幅减少显存使用。6G显存可以开启
$train_text_encoder_only = 0 # train Text Encoder only | 仅训练 文本编码器
$stop_text_encoder_training = 0 # stop training text encoder after n steps | 在 N 步后停止训练文本编码器，N 表示步数

$noise_offset = 0.1 # noise offset | 在训练中添加噪声偏移来改良生成非常暗或者非常亮的图像，如果启用，推荐参数为 0.1
$keep_tokens = 0 # keep heading N tokens when shuffling caption tokens | 在随机打乱 tokens 时，保留前 N 个不变。

# Learning rate | 学习率
$lr = "1e-4"
$unet_lr = "1e-4" # Unet learning rate | 该参数在 AdaFactor 优化器中无效
$text_encoder_lr = "1e-5" # text encoder learning rate | 该参数在 AdaFactor 优化器中无效
$lr_scheduler = "cosine_with_restarts" # "linear", "cosine", "cosine_with_restarts", "polynomial", "constant", "constant_with_warmup"
$lr_warmup_steps = 0 # warmup steps | 仅在 lr_scheduler 为 constant_with_warmup 时需要填写这个值
$lr_restart_cycles = 10 # cosine_with_restarts restart cycles | 余弦退火重启次数，仅在 lr_scheduler 为 cosine_with_restarts 时起效。

# Output settings | 输出设置
$output_name = "aki" # output model name | 模型保存名称
$save_precision = "fp16" # model precision | 保存模型时的精度 默认为 fp16 可用参数有 float fp16 bf16 (本参数对于 DreamBooth 和 Diffusers 样式下的 fine tuning 训练方法所导出的模型无效)
$save_model_as = "safetensors" # model save ext | 模型保存格式 ckpt, pt, safetensors

# Resume training state | 恢复训练设置  
$save_training_state = "" # save training state | 保存训练状态 本参数需要指定保存的文件夹位置 名称类似于 <output_name>-??????-state ?????? 表示 epoch 数
$resume = "" # resume from state | 从某个状态文件夹中恢复训练 需配合上方参数同时使用 由于规范文件限制 epoch 数和全局步数不会保存 即使恢复时它们也从 1 开始 与 network_weights 的具体实现操作并不一致

# 其他设置
$network_weights = "" # pretrained weights for LoRA network | 若需要从已有的 LoRA 模型上继续训练，请填写 LoRA 模型路径。 本设置与恢复训练参数不兼容使用
$min_bucket_reso = 256 # arb min resolution | arb 最小分辨率
$max_bucket_reso = 1024 # arb max resolution | arb 最大分辨率
$persistent_data_loader_workers = 0 # persistent dataloader workers | 容易爆内存，保留加载训练集的worker，减少每个 epoch 之间的停顿
$clip_skip = 2 # clip skip | 玄学 一般用 2 底模模型版本为 2.0 时无效

# optimizer settings | optimizer 优化器设置 (有且只能使用一种优化器 默认为 8bit adam)
# 编者注 理论上该插件允许使用 torch 包内的所有优化器和其他包内已包含的优化器 torch 自带的优化器相关文档地址：https://pytorch.org/docs/stable/optim.html
# 需要注意的是 每次训练有且仅能启用一个优化器 8bit adam 优先级最高
$use_8bit_adam = 1 # use 8bit adam optimizer | 使用 8bit adam 优化器节省显存，默认启用。部分 10 系老显卡无法使用，修改为 0 禁用。
$use_lion = 0 # use lion optimizer | 使用 Lion 优化器
$use_dadaptation = 0 # use dadaptation optimizer | 使用 D-Adaptation 优化器 使用该优化器时 建议使用大学习率 推荐1.0/1.0/1.0 使用前需提前执行 pip install dadaptation
$use_adam = 0 # use AdamW optimizer | 使用 AdamW 优化器 非 8bit 版
$use_sgdnesterov = 0 # use SGDNesterov optimizer | 使用 SGDNesterov 优化器
$use_8bit_sgdnesterov = 0 # use 8bit SGDNesterov opitimizer | 使用 8bit SGDNesterov 优化器
$use_adafactor = 0 # use AdaFactor opitimizer | 使用 AdaFactor 优化器 该优化器会无视 unet_lr/text_encoder_lr 参数 使用 lr 作为初始学习率


# LoCon & LoHa 训练设置
$use_locon_module = 0 # enable old LoCon module | 启用 LoCon 模块进行训练 该方法已经被弃用 仅限用于对比使用 需自行安装相关依赖
$use_lycoris_module = 0 # enable LyCORIS module | 启用 LyCORIS 模块进行训练
$enable_locon_train = 0 # enable LoCon train | 启用 LoCon 训练 启用后 network_dim 和 network_alpha 应当选择较小的值，比如 2~16 但根据实际训练情况来看 可以在初期训练时使用较大的 rank 数 后续可裁剪成需要的 rank 编者这里用的参数是 64 / 64
$enable_loha_train = 0 # enable LoHa train | 启用 LoHa 训练 该算法属于新的 LoCon 共用 LoCon 参数 且两者不能同时启用
$conv_dim = 32 # conv dim | 类似于 network_dim，推荐为 4
$conv_alpha = 32 # conv alpha | 类似于 network_alpha，可以采用与 conv_dim 一致或者更小的值


# LoRA & LoHa 附加参数
$dropout = 0.4 # dropout rate | 防过拟合措施之一 随机丢弃部分图像 取值范围 0-1 本参数仅限 LoRA 可用
$algo = "lora" # algorithm | 使用的算法 standard 表示传统 LoRA (networks.lora) lora 表示传统 LoCon (locon.locon_kohya / lycoris.kohya) ; loha 表示新 LoCon (LoHa) 算法 需配合使用 ; ia3 表示新的 LoHa 算法 lokr 表示 LoKR 算法 作者在 2023/04/08 新更新的一个算法 其中 ia3/LoKR 算法需要源码安装 LyCORIS 项目或使用开发版 pip 安装包进行操作 ia3/lokr 算法属于实验性功能 locon.locon_kohya 属于废弃方法中的一种 需要切换到 locon_archive 分支安装使用 已知 pypi 已将该包定义为 deprecated 不推荐使用 仅用于对比实验

# Other Settings | 其他设置
$max_token_length = 255 # max token length | 最大提示词长度 本参数在默认情况下为 255 可设置成 75 125 等 该参数较为玄学 建议在不清楚该参数会怎么影响模型生成的情况下保持默认值即可
$mixed_precision = "fp16" # mixed_precision | 混合精度 有 bf16 fp16 no 三个参数  RTX30 系及其以后世代的显卡可以使用 bf16 参数 但需同步调整相关参数器使用 默认为 fp16 (讲白话就是这个玩意是省显存用的)
$seed = "1337" # seed number | 种子数 如果不知道具体作用保持默认值 1337 不动

# ============= DO NOT MODIFY CONTENTS BELOW | 请勿修改下方内容 =====================
# Activate python venv
.\venv\Scripts\activate

$Env:HF_HOME = "huggingface"
$network_module = "networks.lora"
$ext_args = [System.Collections.ArrayList]::new()

if ($train_unet_only) {
  [void]$ext_args.Add("--network_train_unet_only")
}

if ($seed) {
  [void]$ext_args.Add("--seed=$seed")
}

if ($is_v2_model){
  [void]$ext_args.Add("--v2")
}

if ($parameterization){
  [void]$ext_args.Add("--v_parameterization")
}

if ($train_text_encoder_only) {
  [void]$ext_args.Add("--network_train_text_encoder_only")
}

if ($network_weights) {
  [void]$ext_args.Add("--network_weights=" + $network_weights)
}

if ($save_training_state) {
  [void]$ext_args.Add("--save_training_state=" + $save_training_state)
}

if ($resume) {
  [void]$ext_args.Add("--resume=" + $resume)
}

if ($network_module -eq "networks.lora" -and $algo) {
  if ($dropout) {
    [void]$ext_args.Add("--network_args")
    [void]$ext_args.Add("algo=$algo")
    [void]$ext_args.Add("dropout=$dropout")
  }
  else {
    [void]$ext_args.Add("--network_args")
    [void]$ext_args.Add("algo=$algo") 
  } 
}

if ($reg_data_dir) {
  [void]$ext_args.Add("--reg_data_dir=" + $reg_data_dir)
}

if ($stop_text_encoder_training) {
  [void]$ext_args.Add("--stop_text_encoder_training=$stop_text_encoder_training")
}

if ($use_8bit_adam) {
  [void]$ext_args.Add("--use_8bit_adam")
}

if ($use_lion) {
  [void]$ext_args.Add("--use_lion_optimizer")
}

if ($use_dadaptation){
  [void]$ext_args.Add("--optimizer_type=dadaptation")
}

if ($use_8bit_sgdnesterov){
  [void]$ext_args.Add("--optimizer_type=SGDNesterov8bit")
}

if ($use_sgdnesterov){
  [void]$ext_args.Add("--optimizer_type=SGDNesterov")
}

if ($use_adam){
  [void]$ext_args.Add("--optimizer_type=Adam")
}

if ($use_adafactor){
  [void]$ext_args.Add("--optimizer_type=AdaFactor")
}

if ($persistent_data_loader_workers) {
  [void]$ext_args.Add("--persistent_data_loader_workers")
}

if (($enable_locon_train -eq 1) -and ($use_lycoris_module -eq 1)) {
  $network_module = "lycoris_kohya"
  [void]$ext_args.Add("--network_args")
  [void]$ext_args.Add("conv_dim=$conv_dim")
  [void]$ext_args.Add("conv_alpha=$conv_alpha")
}

if (($enbale_locon_train -eq 1) -and ($use_lycoris_module -eq 0)) {
  $network_module = "networks.lora"
  [void]$ext_args.Add("--network_args")
  [void]$ext_args.Add("conv_dim=$conv_dim")
  [void]$ext_args.Add("conv_alpha=$conv_alpha")
}

if (($enable_locon_train -eq 1) -and ($enable_locon_module -eq 1)) {
  $network_module = "locon.locon_kohya"
  [void]$ext_args.Add("--network_args")
  [void]$ext_args.Add("conv_dim=$conv_dim")
  [void]$ext_args.Add("conv_alpha=$conv_alpha")
}

if ($enable_loha_train){
  $network_module = "lycoris.kohya"
  [void]$ext_args.Add("--network_args")
  [void]$ext_args.Add("conv_dim=$conv_dim")
  [void]$ext_args.Add("conv_alpha=$conv_alpha")
  [void]$ext_args.Add("algo=$algo")
}

if ($max_train_steps -and ($max_train_epoches -eq 0)){
  [void]$ext_args.Add("--max_train_steps=$max_train_steps")
}
else {
  [void]$ext_args.Add("--max_train_epoches=$max_train_epoches")
}

if ($clip_skip -and ($is_v2_model -eq 0)){
  [void]$ext_args.Add("--clip_skip=$clip_skip")
}

if ($noise_offset) {
  [void]$ext_args.Add("--noise_offset=$noise_offset")
}

if ($max_token_length){
  [void]$ext_args.Add("--max_token_length=$max_token_length")
}

if ($mixed_precision){
  [void]$ext_args.Add("--mixed_precision=$mixed_precision")
}

if ($save_precision){
  [void]$ext_args.Add("--save_precision=$save_precision")
}

# run train
accelerate launch --num_cpu_threads_per_process=8 "./sd-scripts/train_network.py" `
  --enable_bucket `
  --pretrained_model_name_or_path=$pretrained_model `
  --train_data_dir=$train_data_dir `
  --output_dir="./output" `
  --logging_dir="./logs" `
  --resolution=$resolution `
  --network_module=$network_module `
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
  --cache_latents `
  --prior_loss_weight=1 `
  --caption_extension=".txt" `
  --save_model_as=$save_model_as `
  --min_bucket_reso=$min_bucket_reso `
  --max_bucket_reso=$max_bucket_reso `
  --keep_tokens=$keep_tokens `
  --xformers --shuffle_caption $ext_args
Write-Output "Train finished"
Read-Host | Out-Null ;
