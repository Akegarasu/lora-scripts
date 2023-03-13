# LoRA resize script by @bdsqlsz

$save_precision = "fp16" # precision in saving, default float | 保存精度, 可选 float、fp16、bf16, 默认 float
$new_rank = 4 # dim rank of output LoRA | dim rank等级, 默认 4
$model = "./output/lora_name.safetensors" # original LoRA model path need to resize, save as cpkt or safetensors | 需要调整大小的模型路径, 保存格式 cpkt 或 safetensors
$save_to = "./output/lora_name_new.safetensors" # output LoRA model path, save as ckpt or safetensors | 输出路径, 保存格式 cpkt 或 safetensors
$device = "cuda" # device to use, cuda for GPU | 使用 GPU跑, 默认 CPU
$verbose = 1 # display verbose resizing information | rank变更时, 显示详细信息
$dynamic_method = "" # Specify dynamic resizing method, --new_rank is used as a hard limit for max rank | 动态调节大小，可选"sv_ratio", "sv_fro", "sv_cumulative",默认无
$dynamic_param = "" # Specify target for dynamic reduction | 动态参数,sv_ratio模式推荐1~2, sv_cumulative模式0~1, sv_fro模式0~1, 比sv_cumulative要高


# Activate python venv
.\venv\Scripts\activate

$Env:HF_HOME = "huggingface"
$ext_args = [System.Collections.ArrayList]::new()

if ($verbose) {
  [void]$ext_args.Add("--verbose")
}

if ($dynamic_method) {
  [void]$ext_args.Add("--dynamic_method=" + $dynamic_method)
}

if ($dynamic_param) {
  [void]$ext_args.Add("--dynamic_param=" + $dynamic_param)
}

# run resize
accelerate launch --num_cpu_threads_per_process=8 "./sd-scripts/networks/resize_lora.py" `
	--save_precision=$save_precision `
	--new_rank=$new_rank `
	--model=$model `
	--save_to=$save_to `
	--device=$device `
	$ext_args 

Write-Output "Resize finished"
Read-Host | Out-Null ;
