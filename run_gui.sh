#!/bin/bash

#export HF_HOME=huggingface
export HF_ENDPOINT=https://hf-mirror.com  #为国内网络环境做替换，解决无法识别t5xxl-V1的问题
export PYTHONUTF8=1

python gui.py "$@"

