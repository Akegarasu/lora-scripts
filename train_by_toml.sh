#!/bin/bash
# LoRA train script by @Akegarasu

config_file="./config/default.toml"          # config_file | 使用toml文件指定训练参数
sample_prompts="./config/sample_prompts.txt" # sample_prompts | 采样prompts文件,留空则不启用采样功能

sdxl=0                                     # sdxl option | 添加SDXL选项，默认禁用
multi_gpu=0                                # multi gpu | 多显卡训练 该参数仅限在显卡数 >= 2 使用

# ============= DO NOT MODIFY CONTENTS BELOW | 请勿修改下方内容 =====================

export HF_HOME="huggingface"
export TF_CPP_MIN_LOG_LEVEL=3
export PYTHONUTF8=1

extArgs=()
launchArgs=()

if [[ $multi_gpu == 1 ]]; then launchArgs+=("--multi_gpu"); fi
if [[ $sdxl == 1 ]]; then launchArgs+=("--sdxl"); fi

# run train
if [[ $sdxl == 1 ]]; then
  script_name="sdxl_train_network.py"
else
  script_name="train_network.py"
fi

python -m accelerate.commands.launch "${launchArgs[@]}" --num_cpu_threads_per_process=8 "./sd-scripts/$script_name" \
  --config_file="$config_file" \
  --sample_prompts="$sample_prompts" \
  "${extArgs[@]}"
