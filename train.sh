# LoRA train script by @Akegarasu

# Train data path | 设置训练用模型、图片
export pretrained_model="./sd-models/model.ckpt" # base model path | 底模路径
export train_data_dir="./train/aki" # train dataset path | 训练数据集路径

# Train related params | 训练相关参数
export resolution="512,512" # image resolution w,h. 图片分辨率，宽,高。支持非正方形，但必须是 64 倍数。
export batch_size=1 # batch size
export max_train_epoches=10 # max train epoches | 最大训练 epoch
export save_every_n_epochs=2 # save every n epochs | 每 N 个 epoch 保存一次
export network_dim=32 # network dim | 常用 4~128，不是越大越好
export network_alpha=16 # network alpha | 常用与 network_dim 相同的值或者采用较小的值，如 network_dim的一半 防止下溢。默认值为 1，使用较小的 alpha 需要提升学习率。
export clip_skip=2 # clip skip | 玄学 一般用 2
export train_unet_only=0 # train U-Net only | 仅训练 U-Net，开启这个会牺牲效果大幅减少显存使用。6G显存可以开启
export train_text_encoder_only=0 # train Text Encoder only | 仅训练 文本编码器

# Learning rate | 学习率
export lr="1e-4"
export unet_lr="1e-4"
export text_encoder_lr="1e-5"
export lr_scheduler="cosine_with_restarts" # "linear", "cosine", "cosine_with_restarts", "polynomial", "constant", "constant_with_warmup"

# Output settings | 输出设置
export output_name="aki" # output model name | 模型保存名称
export save_model_as="safetensors" # model save ext | 模型保存格式 ckpt, pt, safetensors



export HF_HOME="huggingface"
export TF_CPP_MIN_LOG_LEVEL=3

accelerate launch --num_cpu_threads_per_process=8 "./sd-scripts/train_network.py" \
  --enable_bucket \
  --pretrained_model_name_or_path=$pretrained_model \
  --train_data_dir=$train_data_dir \
  --output_dir="./output" \
  --logging_dir="./logs" \
  --resolution=$resolution \
  --network_module=networks.lora \
  --max_train_epochs=$max_train_epoches \
  --learning_rate=$lr \
  --unet_lr=$unet_lr \
  --text_encoder_lr=$text_encoder_lr \
  --network_dim=$network_dim \
  --network_alpha=$network_alpha \
  --output_name=$output_name \
  --lr_scheduler=$lr_scheduler \
  --train_batch_size=$batch_size \
  --save_every_n_epochs=$save_every_n_epochs \
  --mixed_precision="fp16" \
  --save_precision="fp16" \
  --seed="1337" \
  --cache_latents \
  --clip_skip=$clip_skip \
  --prior_loss_weight=1 \
  --max_token_length=225 \
  --caption_extension=".txt" \
  --save_model_as=$save_model_as \
  --xformers --shuffle_caption --use_8bit_adam