# LoRA train script by @Akegarasu

$multi_gpu = 0		 # multi gpu | 多显卡训练 该参数仅限在显卡数 >= 2 使用
$config_file = "./toml/default.toml"		 # config_file | 使用toml文件指定训练参数
$sample_prompts = "./toml/sample_prompts.txt"		 # sample_prompts | 采样prompts文件,留空则不启用采样功能
$utf8 = 1		 # utf8 | 使用utf-8编码读取toml；以utf-8编码编写的、含中文的toml必须开启


# ============= DO NOT MODIFY CONTENTS BELOW | 请勿修改下方内容 =====================

# Activate python venv
.\venv\Scripts\activate

$Env:HF_HOME = "huggingface"

$ext_args = [System.Collections.ArrayList]::new()
$launch_args = [System.Collections.ArrayList]::new()

if ($multi_gpu) {
  [void]$launch_args.Add("--multi_gpu")
}
if ($utf8 -eq 1) {
  $Env:PYTHONUTF8 = 1
}

# run train
accelerate launch $launch_args --num_cpu_threads_per_process=8 "./sd-scripts/train_network.py" `
  --config_file=$config_file `
  --sample_prompts=$sample_prompts `
  $ext_args

Write-Output "Train finished"
Read-Host | Out-Null ;
