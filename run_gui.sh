#!/bin/bash

source venv/bin/activate

export HF_HOME=huggingface
export PYTHONUTF8=1

python gui.py

