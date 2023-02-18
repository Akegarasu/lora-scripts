# LoRA resize script by @bdsqlsz

$save_precision = "fp16" # precision in saving, default float | 保存精度, 可选 float、fp16、bf16, 默认 float
$new_rank = 4 # dim rank of output LoRA | dim rank等级, 默认 4
$model = "./output/lora_name.safetensors" # original LoRA model path need to resize, save as cpkt or safetensors | 需要调整大小的模型路径, 保存格式 cpkt 或 safetensors
$save_to = "./output/lora_name_new.safetensors" # output LoRA model path, save as ckpt or safetensors | 输出路径, 保存格式 cpkt 或 safetensors
$device = "cuda" # device to use, cuda for GPU | 使用 GPU跑, 默认 CPU
$verbose = 1 # display verbose resizing information | rank变更时, 显示详细信息


# Activate python venv
.\venv\Scripts\activate

$Env:HF_HOME = "huggingface"
$ext_args = [System.Collections.ArrayList]::new()

if ($verbose) {
  [void]$ext_args.Add("--verbose")
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