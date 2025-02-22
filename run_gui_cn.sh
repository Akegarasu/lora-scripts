#!/bin/bash

source "./venv/bin/activate"

export HF_HOME=huggingface
export HF_ENDPOINT=https://hf-mirror.com
export PIP_INDEX_URL="https://pypi.tuna.tsinghua.edu.cn/simple"
export PYTHONUTF8=1

python gui.py "$@"


