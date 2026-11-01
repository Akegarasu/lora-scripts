param(
    [switch]$SkipTorch
)

$ErrorActionPreference = "Stop"
Set-Location (Split-Path -Parent $PSScriptRoot)
$Env:HF_HOME = "huggingface"
$Env:PIP_DISABLE_PIP_VERSION_CHECK = "1"
$Env:PIP_NO_CACHE_DIR = "1"
$Env:PIP_INDEX_URL = "https://pypi.tuna.tsinghua.edu.cn/simple"

function Check-Install([string]$Step) {
    if ($LASTEXITCODE -ne 0) { throw "$Step（退出码 $LASTEXITCODE）" }
}

if (Test-Path -LiteralPath "python/python.exe") {
    Write-Output "使用 python 文件夹内的 Python..."
    $pythonExe = Join-Path (Get-Location) "python/python.exe"
} else {
    if (!(Test-Path -LiteralPath "venv/Scripts/python.exe")) {
        Write-Output "正在创建虚拟环境..."
        python -m venv venv
        Check-Install "创建虚拟环境失败，请检查 Python 版本与 PATH。"
    }
    $pythonExe = Join-Path (Get-Location) "venv/Scripts/python.exe"
}

Write-Output "安装训练依赖（使用国内 PyPI 镜像；PyTorch 使用官方 CUDA 12.8 源）。"
if (!$SkipTorch) {
    & $pythonExe -m pip install torch==2.7.0+cu128 torchvision==0.22.0+cu128 --index-url https://download.pytorch.org/whl/cu128
    Check-Install "PyTorch 安装失败。"
    & $pythonExe -m pip install --no-deps xformers==0.0.30 --index-url https://download.pytorch.org/whl/cu128
    Check-Install "xformers 安装失败。"
}

& $pythonExe -c "import torch; from packaging.version import Version; assert Version(torch.__version__.split('+')[0]) >= Version('2.6'), 'sd-scripts requires PyTorch >= 2.6; install the CUDA build matching your GPU first.'"
Check-Install "PyTorch 环境不满足要求。"
& $pythonExe -m pip install --upgrade -r requirements.txt
Check-Install "训练界面依赖安装失败。"
Write-Output "安装完毕"
