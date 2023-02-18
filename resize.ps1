# LoRA resize script by @bdsqlsz

$save_precision = "bf16" # precision in saving, default float | 保存精度,可选float、fp16、bf16,不选默认float
$new_rank = 4 # dim rank of output LoRA | dim rank等级,默认4
$model = "./output/aruru_otsuki(starlight).safetensors" #original Lora model need to resize,save as cpkt or safetensors| 需要压缩的模型地址,保存格式cpkt或safetensors
$save_to = "./output/aruru_otsuki(starlight)_s.safetensors" # output Lora model,save as ckpt or safetensors  |输出地址,保存格式cpkt或safetensors
$device = "cuda" #device to use, cuda for GPU | 使用cuda GPU跑,不选默认CPU
$verbose = 1 #Display verbose resizing information | rank变更时,显示详细信息


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