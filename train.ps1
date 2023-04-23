# LoRA train script by @Akegarasu

# Train data path | ����ѵ����ģ�͡�ͼƬ
$pretrained_model = "./sd-models/model.ckpt" # base model path | ��ģ·��
$is_v2_model = 0 # SD2.0 model | SD2.0ģ�� 2.0ģ���� clip_skip Ĭ����Ч
$parameterization = 0 # parameterization | ������ ��������Ҫ�� V2 ����ͬ��ʹ�� ʵ���Թ���
$train_data_dir = "./train/aki" # train dataset path | ѵ�����ݼ�·��
$reg_data_dir = "" # directory for regularization images | �������ݼ�·����Ĭ�ϲ�ʹ������ͼ��

# Network settings | ��������
$network_module = "networks.lora" # �����ｫ������ѵ�����������࣬Ĭ��Ϊ networks.lora Ҳ���� LoRA ѵ�����������ѵ�� LyCORIS��LoCon��LoHa�� �ȣ����޸����ֵΪ lycoris.kohya
$network_weights = "" # pretrained weights for LoRA network | ����Ҫ�����е� LoRA ģ���ϼ���ѵ��������д LoRA ģ��·����
$network_dim = 32 # network dim | ���� 4~128������Խ��Խ��
$network_alpha = 32 # network alpha | ������ network_dim ��ͬ��ֵ���߲��ý�С��ֵ���� network_dim��һ�� ��ֹ���硣Ĭ��ֵΪ 1��ʹ�ý�С�� alpha ��Ҫ����ѧϰ�ʡ�

# Train related params | ѵ����ز���
$resolution = "512,512" # image resolution w,h. ͼƬ�ֱ��ʣ���,�ߡ�֧�ַ������Σ��������� 64 ������
$batch_size = 1 # batch size
$max_train_epoches = 10 # max train epoches | ���ѵ�� epoch
$save_every_n_epochs = 2 # save every n epochs | ÿ N �� epoch ����һ��

$train_unet_only = 0 # train U-Net only | ��ѵ�� U-Net���������������Ч����������Դ�ʹ�á�6G�Դ���Կ���
$train_text_encoder_only = 0 # train Text Encoder only | ��ѵ�� �ı�������
$stop_text_encoder_training = 0 # stop text encoder training | �ڵ�N��ʱֹͣѵ���ı�������

$noise_offset = 0 # noise offset | ��ѵ�����������ƫ�����������ɷǳ������߷ǳ�����ͼ��������ã��Ƽ�����Ϊ 0.1
$keep_tokens = 0 # keep heading N tokens when shuffling caption tokens | ��������� tokens ʱ������ǰ N �����䡣
$min_snr_gamma = 0 # minimum signal-to-noise ratio (SNR) value for gamma-ray | ٤�������¼�����С����ȣ�SNR��ֵ  Ĭ��Ϊ 0

# Learning rate | ѧϰ��
$lr = "1e-4"
$unet_lr = "1e-4"
$text_encoder_lr = "1e-5"
$lr_scheduler = "cosine_with_restarts" # "linear", "cosine", "cosine_with_restarts", "polynomial", "constant", "constant_with_warmup"
$lr_warmup_steps = 0 # warmup steps | ѧϰ��Ԥ�Ȳ�����lr_scheduler Ϊ constant �� adafactor ʱ��ֵ��Ҫ��Ϊ0��
$lr_restart_cycles = 1 # cosine_with_restarts restart cycles | �����˻��������������� lr_scheduler Ϊ cosine_with_restarts ʱ��Ч��

# Output settings | �������
$output_name = "aki" # output model name | ģ�ͱ�������
$save_model_as = "safetensors" # model save ext | ģ�ͱ����ʽ ckpt, pt, safetensors

# Resume training state | �ָ�ѵ������  
$save_state = 0 # save training state | ����ѵ��״̬ ���������� <output_name>-??????-state ?????? ��ʾ epoch ��
$resume = "" # resume from state | ��ĳ��״̬�ļ����лָ�ѵ�� ������Ϸ�����ͬʱʹ�� ���ڹ淶�ļ����� epoch ����ȫ�ֲ������ᱣ�� ��ʹ�ָ�ʱ����Ҳ�� 1 ��ʼ �� network_weights �ľ���ʵ�ֲ�������һ��

# ��������
$min_bucket_reso = 256 # arb min resolution | arb ��С�ֱ���
$max_bucket_reso = 1024 # arb max resolution | arb ���ֱ���
$persistent_data_loader_workers = 0 # persistent dataloader workers | ���ױ��ڴ棬��������ѵ������worker������ÿ�� epoch ֮���ͣ��
$clip_skip = 2 # clip skip | ��ѧ һ���� 2
$multi_gpu = 0 # multi gpu | ���Կ�ѵ�� �ò����������Կ��� >= 2 ʹ��
$lowram = 0 # lowram mode | ���ڴ�ģʽ ��ģʽ�»Ὣ U-net �ı������� VAE ת�Ƶ� GPU �Դ��� ���ø�ģʽ���ܻ���Դ���һ��Ӱ��

# �Ż�������
$optimizer_type = "AdamW8bit" # Optimizer type | �Ż������� Ĭ��Ϊ AdamW8bit����ѡ��AdamW AdamW8bit Lion SGDNesterov SGDNesterov8bit DAdaptation AdaFactor

# LyCORIS ѵ������
$algo = "lora" # LyCORIS network algo | LyCORIS �����㷨 ��ѡ lora��loha��lokr��ia3��dylora��lora��Ϊlocon
$conv_dim = 4 # conv dim | ������ network_dim���Ƽ�Ϊ 4
$conv_alpha = 4 # conv alpha | ������ network_alpha�����Բ����� conv_dim һ�»��߸�С��ֵ
$dropout = "0"  # dropout | dropout ����, 0 Ϊ��ʹ�� dropout, Խ���� dropout Խ�࣬�Ƽ� 0~0.5�� LoHa/LoKr/(IA)^3��ʱ��֧��

# Զ�̼�¼����
$use_wandb = 0 # use_wandb | ����wandbԶ�̼�¼����
$wandb_api_key = "" # wandb_api_key | API,ͨ��https://wandb.ai/authorize��ȡ
$log_tracker_name = "" # log_tracker_name | wandb��Ŀ����,������Ϊ"network_train"

# ============= DO NOT MODIFY CONTENTS BELOW | �����޸��·����� =====================
# Activate python venv
.\venv\Scripts\activate

$Env:HF_HOME = "huggingface"
$ext_args = [System.Collections.ArrayList]::new()
$launch_args = [System.Collections.ArrayList]::new()

if ($multi_gpu) {
  [void]$launch_args.Add("--multi_gpu")
}

if ($lowram) {
  [void]$ext_args.Add("--lowram")
}

if ($is_v2_model) {
  [void]$ext_args.Add("--v2") 
}
else {
  [void]$ext_args.Add("--clip_skip=$clip_skip")
}

if ($parameterization) {
  [void]$ext_args.Add("--v_parameterization")
}

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

if ($optimizer_type) {
  [void]$ext_args.Add("--optimizer_type=" + $optimizer_type)
}

if ($optimizer_type -eq "DAdaptation") {
  [void]$ext_args.Add("--optimizer_args")
  [void]$ext_args.Add("decouple=True")
}

if ($network_module -eq "lycoris.kohya") {
  [void]$ext_args.Add("--network_args")
  [void]$ext_args.Add("conv_dim=$conv_dim")
  [void]$ext_args.Add("conv_alpha=$conv_alpha")
  [void]$ext_args.Add("algo=$algo")
  [void]$ext_args.Add("dropout=$dropout")
}

if ($noise_offset -ne 0) {
  [void]$ext_args.Add("--noise_offset=$noise_offset")
}

if ($stop_text_encoder_training -ne 0) {
  [void]$ext_args.Add("--stop_text_encoder_training=$stop_text_encoder_training")
}

if ($save_state -eq 1) {
  [void]$ext_args.Add("--save_state")
}

if ($resume) {
  [void]$ext_args.Add("--resume=" + $resume)
}

if ($min_snr_gamma -ne 0) {
  [void]$ext_args.Add("--min_snr_gamma=$min_snr_gamma")
} 

if($persistent_data_loader_workers) {
  [void]$ext_args.Add("--persistent_data_loader_workers")
}

if ($use_wandb -eq 1) {
  [void]$ext_args.Add("--log_with=all")
}
else {
  [void]$ext_args.Add("--log_with=tensorboard")
}

if ($wandb_api_key) {
  [void]$ext_args.Add("--wandb_api_key=" + $wandb_api_key)
}

if ($log_tracker_name) {
  [void]$ext_args.Add("--log_tracker_name=" + $log_tracker_name)
}

# run train
accelerate launch $launch_args --num_cpu_threads_per_process=8 "./sd-scripts/train_network.py" `
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
