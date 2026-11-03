param(
    [switch]$SkipTorch,
    [ValidateSet("cu130", "cu128")]
    [string]$Cuda = "cu130"
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

$minimumMinor = if (!$SkipTorch -and $Cuda -eq "cu130") { 11 } else { 10 }
& $pythonExe -c "import sys; minimum = (3, int(sys.argv[1])); sys.exit('Python 3.%s+ is required; use -Cuda cu128 for Python 3.10.' % sys.argv[1]) if sys.version_info < minimum else None" $minimumMinor
Check-Install "Python 版本不满足要求。"
& $pythonExe -m pip install --upgrade -r requirements/tooling.txt
Check-Install "打包工具安装失败。"

Write-Output "安装训练依赖（使用国内 PyPI 镜像；PyTorch 使用官方 $Cuda 源）。"
if (!$SkipTorch) {
    # CUDA indexes can publish different xformers wheels under the same version.
    & $pythonExe -m pip install --upgrade --force-reinstall -r "requirements/pytorch-$Cuda.txt" --index-url "https://download.pytorch.org/whl/$Cuda"
    Check-Install "PyTorch 和 xformers 安装失败（$Cuda）。"
}

& $pythonExe -c "import torch; from packaging.version import Version; assert Version(torch.__version__.split('+')[0]) >= Version('2.6'), 'sd-scripts requires PyTorch >= 2.6; install the CUDA build matching your GPU first.'"
Check-Install "PyTorch 环境不满足要求。"
$dependencyArguments = @("--upgrade", "-r", "requirements.txt", "-r", "requirements/tooling.txt")
if (!$SkipTorch) {
    $dependencyArguments += @("-r", "requirements/onnxruntime-$Cuda.txt", "-c", "requirements/pytorch-$Cuda.txt")
}
& $pythonExe -m pip install @dependencyArguments
Check-Install "训练界面依赖安装失败。"
Write-Output "安装完毕"
