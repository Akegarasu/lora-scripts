# LoRA svd_merge script by @bdsqlsz

$save_precision = "fp16" # precision in saving, default float | 保存精度, 可选 float、fp16、bf16, 默认 和源文件相同
$precision = "float" # precision in merging (float is recommended) | 合并时计算精度, 可选 float、fp16、bf16, 推荐float
$new_rank = 4 # dim rank of output LoRA | dim rank等级, 默认 4
$models = "./output/lora_name.safetensors" # original LoRA model path need to resize, save as cpkt or safetensors | 需要合并的模型路径, 保存格式 cpkt 或 safetensors
$ratios = "" # display verbose resizing information | rank变更时, 显示详细信息
$save_to = "./output/lora_name_new.safetensors" # output LoRA model path, save as ckpt or safetensors | 输出路径, 保存格式 cpkt 或 safetensors
$device = "cuda" # device to use, cuda for GPU | 使用 GPU跑, 默认 CPU

# Activate python venv
.\venv\Scripts\activate

$Env:HF_HOME = "huggingface"
$ext_args = [System.Collections.ArrayList]::new()

if ($verbose) {
  [void]$ext_args.Add("--verbose")
}

# run resize
accelerate launch --num_cpu_threads_per_process=8 "./sd-scripts/networks/merge_lora.py" `
	--save_precision=$save_precision `
	--new_rank=$new_rank `
	--models=$model `
  --ratios=$ratios `
	--save_to=$save_to `
	--device=$device `
	$ext_args 

Write-Output "Merge finished"
Read-Host | Out-Null ;
