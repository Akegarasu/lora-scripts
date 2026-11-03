#!/usr/bin/env bash
set -euo pipefail

script_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
project_dir="$(dirname -- "$script_dir")"
create_venv=true
skip_torch=false
cuda_flavor=cu130

while (( $# > 0 )); do
    case "$1" in
        --disable-venv) create_venv=false; shift ;;
        --skip-torch) skip_torch=true; shift ;;
        --cuda)
            if [[ $# -lt 2 || ( "$2" != cu130 && "$2" != cu128 ) ]]; then
                echo "Usage: $0 [--disable-venv] [--skip-torch] [--cuda cu130|cu128]" >&2
                exit 2
            fi
            cuda_flavor="$2"
            shift 2
            ;;
        *) echo "Unknown option: $1" >&2; exit 2 ;;
    esac
done

cd "$project_dir"
if ! python_exe=$(command -v python3 || command -v python); then
    echo "Python 3.11+ is required for cu130; Python 3.10 is supported with --cuda cu128." >&2
    exit 1
fi
if $create_venv; then
    if [[ ! -f venv/bin/python ]]; then
        "$python_exe" -m venv venv
    fi
    source venv/bin/activate
    python_exe="$project_dir/venv/bin/python"
fi

minimum_minor=10
if ! $skip_torch && [[ "$cuda_flavor" == cu130 ]]; then
    minimum_minor=11
fi
"$python_exe" -c "import sys; minimum = (3, int(sys.argv[1])); sys.exit('Python 3.%s+ is required; use --cuda cu128 for Python 3.10.' % sys.argv[1]) if sys.version_info < minimum else None" "$minimum_minor"
"$python_exe" -m pip install --upgrade -r requirements/tooling.txt

if ! $skip_torch; then
    # CUDA indexes can publish different xformers wheels under the same version.
    "$python_exe" -m pip install --upgrade --force-reinstall -r "requirements/pytorch-$cuda_flavor.txt" \
        --index-url "https://download.pytorch.org/whl/$cuda_flavor"
fi

"$python_exe" -c "import torch; from packaging.version import Version; assert Version(torch.__version__.split('+')[0]) >= Version('2.6'), 'sd-scripts requires PyTorch >= 2.6'"
dependency_args=(--upgrade -r requirements.txt -r requirements/tooling.txt)
if ! $skip_torch; then
    dependency_args+=(-r "requirements/onnxruntime-$cuda_flavor.txt" -c "requirements/pytorch-$cuda_flavor.txt")
fi
"$python_exe" -m pip install "${dependency_args[@]}"
echo "Install completed"
