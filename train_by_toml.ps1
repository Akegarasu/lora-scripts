# LoRA train script by @Akegarasu

$config_file = "./config/default.toml"		 # config_file | 使用toml文件指定训练参数
$sample_prompts = "./config/sample_prompts.txt"		 # sample_prompts | 采样prompts文件,留空则不启用采样功能

$sdxl = 0        # for sdxl model | SDXL 训练
$multi_gpu = 0		 # multi gpu | 多显卡训练 该参数仅限在显卡数 >= 2 使用

# ============= DO NOT MODIFY CONTENTS BELOW | 请勿修改下方内容 =====================

# Activate python venv
.\venv\Scripts\activate

$Env:HF_HOME = "huggingface"
$Env:PYTHONUTF8 = 1

$ext_args = [System.Collections.ArrayList]::new()
$launch_args = [System.Collections.ArrayList]::new()

if ($multi_gpu) {
  [void]$launch_args.Add("--multi_gpu")
}
if ($sdxl) {
  [void]$launch_args.Add("--sdxl")
}

# run train
$script_name = if ($sdxl) { "sdxl_train_network.py" } else { "train_network.py" }
python -m accelerate.commands.launch $launch_args --num_cpu_threads_per_process=8 "./sd-scripts/$script_name" `
  --config_file=$config_file `
  --sample_prompts=$sample_prompts `
  $ext_args

Write-Output "Train finished"
Read-Host | Out-Null
