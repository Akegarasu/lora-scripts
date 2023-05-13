# LoRA train script by @Akegarasu

$multi_gpu = 0		 # multi gpu | ���Կ�ѵ�� �ò����������Կ��� >= 2 ʹ��
$config_file = "./toml/default.toml"		 # config_file | ʹ��toml�ļ�ָ��ѵ������
$sample_prompts = "./toml/sample_prompts.txt"		 # sample_prompts | ����prompts�ļ�,���������ò�������
$utf8 = 1		 # utf8 | ʹ��utf-8�����ȡtoml����utf-8�����д�ġ������ĵ�toml���뿪��


# ============= DO NOT MODIFY CONTENTS BELOW | �����޸��·����� =====================

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
python -m accelerate.commands.launch $launch_args --num_cpu_threads_per_process=8 "./sd-scripts/train_network.py" `
  --config_file=$config_file `
  --sample_prompts=$sample_prompts `
  $ext_args

Write-Output "Train finished"
Read-Host | Out-Null ;
