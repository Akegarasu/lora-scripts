#!/bin/bash
# tagger script by @bdsqlsz
# Train data path
train_data_dir="./input" # input images path | 图片输入路径
repo_id="SmilingWolf/wd-v1-4-swinv2-tagger-v2" # model repo id from huggingface |huggingface模型repoID
model_dir="" # model dir path | 本地模型文件夹路径
batch_size=12 # batch size in inference 批处理大小，越大越快
max_data_loader_n_workers=0 # enable image reading by DataLoader with this number of workers (faster) | 0最快
thresh=0.35 # concept thresh | 最小识别阈值
general_threshold=0.35 # general threshold | 总体识别阈值 
character_threshold=0.1 # character threshold | 人物姓名识别阈值
remove_underscore=0 # remove_underscore | 下划线转空格，1为开，0为关 
undesired_tags="" # no need tags | 排除标签
recursive=0 # search for images in subfolders recursively | 递归搜索下层文件夹，1为开，0为关
frequency_tags=0 # order by frequency tags | 从大到小按识别率排序标签，1为开，0为关


# ============= DO NOT MODIFY CONTENTS BELOW | 请勿修改下方内容 =====================

export HF_HOME="huggingface"
export TF_CPP_MIN_LOG_LEVEL=3
extArgs=()

if [ -n "$repo_id" ]; then
  extArgs+=( "--repo_id=$repo_id" )
fi

if [ -n "$model_dir" ]; then
  extArgs+=( "--model_dir=$model_dir" )
fi

if [[ $batch_size -ne 0 ]]; then
  extArgs+=( "--batch_size=$batch_size" )
fi

if [ -n "$max_data_loader_n_workers" ]; then
  extArgs+=( "--max_data_loader_n_workers=$max_data_loader_n_workers" )
fi

if [ -n "$general_threshold" ]; then
  extArgs+=( "--general_threshold=$general_threshold" )
fi

if [ -n "$character_threshold" ]; then
  extArgs+=( "--character_threshold=$character_threshold" )
fi

if [ "$remove_underscore" -eq 1 ]; then
  extArgs+=( "--remove_underscore" )
fi

if [ -n "$undesired_tags" ]; then
  extArgs+=( "--undesired_tags=$undesired_tags" )
fi

if [ "$recursive" -eq 1 ]; then
  extArgs+=( "--recursive" )
fi

if [ "$frequency_tags" -eq 1 ]; then
  extArgs+=( "--frequency_tags" )
fi


# run tagger
accelerate launch --num_cpu_threads_per_process=8 "./sd-scripts/finetune/tag_images_by_wd14_tagger.py" \
  $train_data_dir \
  --thresh=$thresh \
  --caption_extension .txt \
  ${extArgs[@]}
