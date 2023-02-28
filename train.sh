# LoRA train script by @Akegarasu

# Train data path | 设置训练用模型、图片
pretrained_model="./sd-models/model.ckpt" # base model path | 底模路径
train_data_dir="./train/aki" # train dataset path | 训练数据集路径
reg_data_dir="" # directory for regularization images | 正则化数据集路径，默认不使用正则化图像。

# Train related params | 训练相关参数
resolution="512,512" # image resolution w,h. 图片分辨率，宽,高。支持非正方形，但必须是 64 倍数。
batch_size=1 # batch size
max_train_epoches=10 # max train epoches | 最大训练 epoch
save_every_n_epochs=2 # save every n epochs | 每 N 个 epoch 保存一次
network_dim=32 # network dim | 常用 4~128，不是越大越好
network_alpha=32 # network alpha | 常用与 network_dim 相同的值或者采用较小的值，如 network_dim的一半 防止下溢。默认值为 1，使用较小的 alpha 需要提升学习率。
clip_skip=2 # clip skip | 玄学 一般用 2
train_unet_only=0 # train U-Net only | 仅训练 U-Net，开启这个会牺牲效果大幅减少显存使用。6G显存可以开启
train_text_encoder_only=0 # train Text Encoder only | 仅训练 文本编码器

# Learning rate | 学习率
lr="1e-4"
unet_lr="1e-4"
text_encoder_lr="1e-5"
lr_scheduler="cosine_with_restarts" # "linear", "cosine", "cosine_with_restarts", "polynomial", "constant", "constant_with_warmup"
lr_warmup_steps=0 # warmup steps | 仅在 lr_scheduler 为 constant_with_warmup 时需要填写这个值

# Output settings | 输出设置
output_name="aki" # output model name | 模型保存名称
save_model_as="safetensors" # model save ext | 模型保存格式 ckpt, pt, safetensors

# 其他设置
network_weights="" # pretrained weights for LoRA network | 若需要从已有的 LoRA 模型上继续训练，请填写 LoRA 模型路径。
min_bucket_reso=256 # arb min resolution | arb 最小分辨率
max_bucket_reso=1024 # arb max resolution | arb 最大分辨率
persistent_data_loader_workers=0 # persistent dataloader workers | 容易爆内存，保留加载训练集的worker，减少每个 epoch 之间的停顿

# 优化器设置
use_8bit_adam=1 # use 8bit adam optimizer | 使用 8bit adam 优化器节省显存，默认启用。部分 10 系老显卡无法使用，修改为 0 禁用。
use_lion=0 # use lion optimizer | 使用 Lion 优化器


# ============= DO NOT MODIFY CONTENTS BELOW | 请勿修改下方内容 =====================
export HF_HOME="huggingface"
export TF_CPP_MIN_LOG_LEVEL=3

extArgs=()

if [ $train_unet_only == 1 ]; then extArgs+=("--network_train_unet_only"); fi

if [ $train_text_encoder_only == 1 ]; then extArgs+=("--network_train_text_encoder_only"); fi

if [ $network_weights ]; then extArgs+=("--network_weights $network_weights"); fi

if [ $reg_data_dir ]; then extArgs+=("--reg_data_dir $network_weights"); fi

if [ $use_8bit_adam == 1 ]; then extArgs+=("--use_8bit_adam"); fi

if [ $use_lion == 1 ]; then extArgs+=("--use_lion_optimizer"); fi

if [ $persistent_data_loader_workers == 1 ]; then extArgs+=("--persistent_data_loader_workers"); fi

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
  --lr_scheduler=$lr_scheduler \
  --lr_warmup_steps=$lr_warmup_steps \
  --network_dim=$network_dim \
  --network_alpha=$network_alpha \
  --output_name=$output_name \
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
  --min_bucket_reso=$min_bucket_reso \
  --max_bucket_reso=$max_bucket_reso \
  --xformers --shuffle_caption ${extArgs[@]}