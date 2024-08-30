# LoRA interrogate script by @bdsqlsz

$v2 = 0 # load Stable Diffusion v2.x model / Stable Diffusion 2.x模型读取
$sd_model = "./sd-models/sd_model.safetensors" # Stable Diffusion model to load: ckpt or safetensors file | 读取的基础SD模型, 保存格式 cpkt 或 safetensors
$model = "./output/LoRA.safetensors" # LoRA model to interrogate: ckpt or safetensors file | 需要调查关键字的LORA模型, 保存格式 cpkt 或 safetensors
$batch_size = 64 # batch size for processing with Text Encoder | 使用 Text Encoder 处理时的批量大小，默认16，推荐64/128
$clip_skip = 1 # use output of nth layer from back of text encoder (n>=1) | 使用文本编码器倒数第 n 层的输出，n 可以是大于等于 1 的整数


# Activate python venv
.\venv\Scripts\activate

$Env:HF_HOME = "huggingface"
$ext_args = [System.Collections.ArrayList]::new()

if ($v2) {
  [void]$ext_args.Add("--v2")
}

# run interrogate
accelerate launch --num_cpu_threads_per_process=8 "./scripts/networks/lora_interrogator.py" `
	--sd_model=$sd_model `
	--model=$model `
	--batch_size=$batch_size `
	--clip_skip=$clip_skip `
	$ext_args 

Write-Output "Interrogate finished"
Read-Host | Out-Null ;
