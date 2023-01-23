# LoRA train script by @Akegarasu

# Train data path | 设置训练用模型、图片
$pretrained_model = "./sd-models/model.ckpt" # base model path | 底模路径
$vae = "./sd-models/animevae.pt" # vae path | vae 路径
$train_data_dir = "./train/aki" # train dataset path | 训练数据集路径

# Train related params | 训练相关参数
$resolution = "512,512" # image resolution w,h. 图片分辨率，宽,高。支持非正方形，但必须是 64 倍数。
$batch_size = 1 # batch size
$max_train_epoches = 10 # max train epoches | 最大训练 epoch
$save_every_n_epochs = 2 # save every n epochs | 每 N 个 epoch 保存一次
$network_dim = 32 # network dim
$clip_skip = 2
$train_unet_only = 0 # train U-Net only | 仅训练 U-Net
$train_text_encoder_only = 0 # train Text Encoder only | 仅训练 文本编码器

# Learning rate | 学习率
$lr = "1e-4"
$unet_lr = "1e-4"
$text_encoder_lr = "1e-5"
$lr_scheduler = "cosine_with_restarts" # "linear", "cosine", "cosine_with_restarts", "polynomial", "constant", "constant_with_warmup"

# Output settings | 输出设置
$output_name = "aki" # output model name | 模型保存名称
$save_model_as = "safetensors" # model save ext | 模型保存格式

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

# run train
accelerate launch --num_cpu_threads_per_process=8 "./sd-scripts/train_network.py" `
  --enable_bucket `
  --pretrained_model_name_or_path=$pretrained_model `
  --vae=$vae `
  --train_data_dir=$train_data_dir `
  --output_dir="./output" `
  --logging_dir="./logs" `
  --resolution=$resolution `
  --network_module=networks.lora `
  --max_train_epochs=$max_train_epoches `
  --learning_rate=$lr `
  --unet_lr=$unet_lr `
  --text_encoder_lr=$text_encoder_lr `
  --network_dim=$network_dim `
  --output_name=$output_name `
  --lr_scheduler=$lr_scheduler `
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
  --xformers --shuffle_caption --use_8bit_adam $ext_args

Read-Host | Out-Null ;