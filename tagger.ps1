# tagger script by @bdsqlsz

# Train data path
$train_data_dir = "./input" # input images path | 图片输入路径
$repo_id = "SmilingWolf/wd-v1-4-swinv2-tagger-v2" # model repo id from huggingface |huggingface模型repoID
$model_dir = "" # model dir path | 本地模型文件夹路径
$batch_size = 4 # batch size in inference 批处理大小，越大越快
$max_data_loader_n_workers = 0 # enable image reading by DataLoader with this number of workers (faster) | 0最快
$thresh = 0.35 # concept thresh | 最小识别阈值
$general_threshold = 0.35 # general threshold | 总体识别阈值 
$character_threshold = 0.1 # character threshold | 人物姓名识别阈值
$remove_underscore = 0 # remove_underscore | 下划线转空格，1为开，0为关 
$undesired_tags = "" # no need tags | 排除标签
$recursive = 0 # search for images in subfolders recursively | 递归搜索下层文件夹，1为开，0为关
$frequency_tags = 0 # order by frequency tags | 从大到小按识别率排序标签，1为开，0为关


# Activate python venv
.\venv\Scripts\activate

$Env:HF_HOME = "huggingface"
$Env:XFORMERS_FORCE_DISABLE_TRITON = "1"
$ext_args = [System.Collections.ArrayList]::new()

if ($repo_id) {
  [void]$ext_args.Add("--repo_id=" + $repo_id)
}

if ($model_dir) {
  [void]$ext_args.Add("--model_dir=" + $model_dir)
}

if ($batch_size) {
  [void]$ext_args.Add("--batch_size=" + $batch_size)
}

if ($max_data_loader_n_workers) {
  [void]$ext_args.Add("--max_data_loader_n_workers=" + $max_data_loader_n_workers)
}

if ($general_threshold) {
  [void]$ext_args.Add("--general_threshold=" + $general_threshold)
}

if ($character_threshold) {
  [void]$ext_args.Add("--character_threshold=" + $character_threshold)
}

if ($remove_underscore) {
  [void]$ext_args.Add("--remove_underscore")
}

if ($undesired_tags) {
  [void]$ext_args.Add("--undesired_tags=" + $undesired_tags)
}

if ($recursive) {
  [void]$ext_args.Add("--recursive")
}

if ($frequency_tags) {
  [void]$ext_args.Add("--frequency_tags")
}

# run tagger
accelerate launch --num_cpu_threads_per_process=8 "./sd-scripts/finetune/tag_images_by_wd14_tagger.py" `
  $train_data_dir `
  --thresh=$thresh `
  --caption_extension .txt `
  $ext_args

Write-Output "Tagger finished"
Read-Host | Out-Null ;
