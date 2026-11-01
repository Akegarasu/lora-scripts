#!/usr/bin/env bash
set -euo pipefail

script_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
project_dir="$(dirname -- "$script_dir")"
create_venv=true
skip_torch=false

while (( $# > 0 )); do
    case "$1" in
        --disable-venv) create_venv=false; shift ;;
        --skip-torch) skip_torch=true; shift ;;
        *) echo "Unknown option: $1" >&2; exit 2 ;;
    esac
done

cd "$project_dir"
if $create_venv; then
    if [[ ! -f venv/bin/python ]]; then
        python3 -m venv venv
    fi
    source venv/bin/activate
fi

if ! $skip_torch; then
    cuda_version=$(nvidia-smi 2>/dev/null | grep -oP 'CUDA (?:UMD )?Version: \K[\d.]+' | head -1 || true)
    if [[ -z "$cuda_version" ]]; then
        cuda_version=$(nvcc --version 2>/dev/null | grep -oP 'release \K[\d.]+' | head -1 || true)
    fi
    cuda_major_version=${cuda_version%%.*}
    cuda_minor_version=${cuda_version#*.}
    cuda_minor_version=${cuda_minor_version%%.*}
    echo "CUDA Version: $cuda_version"

    if [[ -n "$cuda_version" ]] && (( cuda_major_version > 12 || (cuda_major_version == 12 && cuda_minor_version >= 8) )); then
        python -m pip install torch==2.7.0+cu128 torchvision==0.22.0+cu128 --index-url https://download.pytorch.org/whl/cu128
        python -m pip install --no-deps xformers==0.0.30 --index-url https://download.pytorch.org/whl/cu128
    else
        echo "Install a matching CUDA build of PyTorch >= 2.6 and torchvision first, then rerun with --skip-torch (detected CUDA: $cuda_version). See docs/moss-image-training.md." >&2
        exit 1
    fi
fi

python -c "import torch; from packaging.version import Version; assert Version(torch.__version__.split('+')[0]) >= Version('2.6'), 'sd-scripts requires PyTorch >= 2.6'"
python -m pip install --upgrade -r requirements.txt
echo "Install completed"
