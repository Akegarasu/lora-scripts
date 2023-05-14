#!/usr/bin/bash

script_dir="$( cd "$( dirname "${BASH_SOURCE[0]}" )" >/dev/null 2>&1 && pwd )"

echo "Creating python venv..."
python3 -m venv venv
source "$script_dir/venv/bin/activate"

echo "Installing torch & xformers..."

cuda_version_line="Cuda compilation tools, release 11.8, V11.8.89"
cuda_version=$(echo $cuda_version_line | sed -n -e 's/^.*release \([0-9]\+\.[0-9]\+\),.*$/\1/p')

echo "Cuda Version:$cuda_version"

if [[ $cuda_version == "11.8" ]]; then
    echo "install torch 2.0.0+cu118"
    pip install torch==2.0.0+cu118 torchvision==0.15.1+cu118 --extra-index-url https://download.pytorch.org/whl/cu118
    pip install xformers==0.0.19
elif [[ $cuda_version == "11.6" ]]; then
    echo "install torch 1.12.1+cu116"
    pip install torch==1.12.1+cu116 torchvision==0.13.1+cu116 --extra-index-url https://download.pytorch.org/whl/cu116
    pip install --upgrade git+https://github.com/facebookresearch/xformers.git@0bad001ddd56c080524d37c84ff58d9cd030ebfd
    pip install triton==2.0.0.dev20221202
else
    echo "Unsupported cuda version:$cuda_version"
    exit 1
fi

echo "Installing deps..."
cd "$script_dir/sd-scripts" || exit

pip install --upgrade -r requirements.txt
pip install --upgrade lion-pytorch lycoris-lora dadaptation fastapi uvicorn wandb

cd "$script_dir" || exit

echo "Install completed"
