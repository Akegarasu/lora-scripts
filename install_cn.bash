#!/usr/bin/bash

script_dir="$( cd "$( dirname "${BASH_SOURCE[0]}" )" >/dev/null 2>&1 && pwd )"
create_venv=true

while [ -n "$1" ]; do
    case "$1" in
        --disable-venv)
            create_venv=false
            shift
            ;;
        *)
            shift
            ;;
    esac
done

if $create_venv; then
    echo "Creating python venv..."
    python3 -m venv venv
    source "$script_dir/venv/bin/activate"
    echo "active venv"
fi

# 设置使用清华源
# MIRROR="https://pypi.tuna.tsinghua.edu.cn/simple"
MIRROR="https://mirrors.aliyun.com/pypi/simple"

echo "Installing torch & xformers using Tsinghua Mirror..."

cuda_version=$(nvidia-smi | grep -oiP 'CUDA Version: \K[\d\.]+')

if [ -z "$cuda_version" ]; then
    cuda_version=$(nvcc --version | grep -oiP 'release \K[\d\.]+')
fi
cuda_major_version=$(echo "$cuda_version" | awk -F'.' '{print $1}')
cuda_minor_version=$(echo "$cuda_version" | awk -F'.' '{print $2}')

echo "CUDA Version: $cuda_version"

pip install -i $MIRROR --upgrade pip

if (( cuda_major_version >= 12 )); then
    echo "install torch 2.4.1 for CUDA 12.x"
    pip install -i $MIRROR torch==2.4.1 torchvision==0.19.1
    pip install -i $MIRROR xformers==0.0.28.post1
elif (( cuda_major_version == 11 && cuda_minor_version >= 8 )); then
    echo "install torch 2.4.0 for CUDA 11.8+"
    pip install -i $MIRROR torch==2.4.0 torchvision==0.19.0
    pip install -i $MIRROR xformers==0.0.27.post2
elif (( cuda_major_version == 11 && cuda_minor_version >= 6 )); then
    echo "install torch 1.12.1 for CUDA 11.6+"
    pip install -i $MIRROR torch==1.12.1 torchvision==0.13.1
    # for RTX3090+cu113/cu116 xformers, we need to install this version from source. You can also try xformers==0.0.18
    pip install -i $MIRROR --upgrade git+https://github.com/facebookresearch/xformers.git@0bad001ddd56c080524d37c84ff58d9cd030ebfd
    pip install -i $MIRROR triton==2.0.0.dev20221202
elif (( cuda_major_version == 11 && cuda_minor_version >= 2 )); then
    echo "install torch 1.12.1 for CUDA 11.2+"
    pip install -i $MIRROR torch==1.12.1 torchvision==0.13.1
    pip install -i $MIRROR --upgrade git+https://github.com/facebookresearch/xformers.git@0bad001ddd56c080524d37c84ff58d9cd030ebfd
    pip install -i $MIRROR triton==2.0.0.dev20221202
else
    echo "Unsupported cuda version:$cuda_version"
    exit 1
fi

echo "Installing deps..."

cd "$script_dir" || exit
pip install -i $MIRROR --upgrade -r requirements.txt

echo "Install completed"
