#!/bin/bash


# 激活虚拟环境
source "./venv/bin/activate"

# 环境变量
export HF_HOME=huggingface
# 国内hg镜像
export HF_ENDPOINT=https://hf-mirror.com
export PYTHONUTF8=1

python gui.py --listen --tensorboard-port 6006 --port 28000 "$@"


