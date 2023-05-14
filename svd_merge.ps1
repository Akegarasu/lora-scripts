# LoRA svd_merge script by @bdsqlsz

$save_precision = "fp16" # precision in saving, default float | 保存精度, 可选 float、fp16、bf16, 默认 和源文件相同
$precision = "float" # precision in merging (float is recommended) | 合并时计算精度, 可选 float、fp16、bf16, 推荐float
$new_rank = 4 # dim rank of output LoRA | dim rank等级, 默认 4
$models = "./output/modelA.safetensors ./output/modelB.safetensors" # original LoRA model path need to resize, save as cpkt or safetensors | 需要合并的模型路径, 保存格式 cpkt 或 safetensors，多个用空格隔开
$ratios = "1.0 -1.0" # ratios for each model / LoRA模型合并比例，数量等于模型数量，多个用空格隔开
$save_to = "./output/lora_name_new.safetensors" # output LoRA model path, save as ckpt or safetensors | 输出路径, 保存格式 cpkt 或 safetensors
$device = "cuda" # device to use, cuda for GPU | 使用 GPU跑, 默认 CPU
$new_conv_rank = 0 # Specify rank of output LoRA for Conv2d 3x3, None for same as new_rank | Conv2d 3x3输出，没有默认同new_rank

# Activate python venv
.\venv\Scripts\activate

$Env:HF_HOME = "huggingface"
$Env:XFORMERS_FORCE_DISABLE_TRITON = "1"
$ext_args = [System.Collections.ArrayList]::new()

[void]$ext_args.Add("--models")
foreach ($model in $models.Split(" ")) {
    [void]$ext_args.Add($model)
}

[void]$ext_args.Add("--ratios")
foreach ($ratio in $ratios.Split(" ")) {
    [void]$ext_args.Add([float]$ratio)
}

if ($new_conv_rank) {
  [void]$ext_args.Add("--new_conv_rank=" + $new_conv_rank)
}

# run svd_merge
accelerate launch --num_cpu_threads_per_process=8 "./sd-scripts/networks/svd_merge_lora.py" `
	--save_precision=$save_precision `
	--precision=$precision `
	--new_rank=$new_rank `
	--save_to=$save_to `
	--device=$device `
	$ext_args 

Write-Output "SVD Merge finished"
Read-Host | Out-Null ;
