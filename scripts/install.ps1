param(
    [switch]$SkipTorch,
    [ValidateSet("cu130", "cu128")]
    [string]$Cuda = "cu130"
)

$ErrorActionPreference = "Stop"
Set-Location (Split-Path -Parent $PSScriptRoot)
$Env:HF_HOME = "huggingface"

function Check-Install([string]$Step) {
    if ($LASTEXITCODE -ne 0) { throw "$Step failed (exit code $LASTEXITCODE)." }
}

if (!(Test-Path -LiteralPath "venv/Scripts/python.exe")) {
    Write-Output "Creating venv for Python..."
    python -m venv venv
    Check-Install "Virtual environment creation"
}
$pythonExe = Join-Path (Get-Location) "venv/Scripts/python.exe"

$minimumMinor = if (!$SkipTorch -and $Cuda -eq "cu130") { 11 } else { 10 }
& $pythonExe -c "import sys; minimum = (3, int(sys.argv[1])); sys.exit('Python 3.%s+ is required; use -Cuda cu128 for Python 3.10.' % sys.argv[1]) if sys.version_info < minimum else None" $minimumMinor
Check-Install "Python compatibility check"
& $pythonExe -m pip install --upgrade -r requirements/tooling.txt
Check-Install "Packaging tool installation"

Write-Output "Installing training dependencies..."
if (!$SkipTorch) {
    # CUDA indexes can publish different xformers wheels under the same version.
    & $pythonExe -m pip install --upgrade --force-reinstall -r "requirements/pytorch-$Cuda.txt" --index-url "https://download.pytorch.org/whl/$Cuda"
    Check-Install "PyTorch and xformers installation ($Cuda)"
}
& $pythonExe -c "import torch; from packaging.version import Version; assert Version(torch.__version__.split('+')[0]) >= Version('2.6'), 'sd-scripts requires PyTorch >= 2.6'"
Check-Install "PyTorch compatibility check"
$dependencyArguments = @("--upgrade", "-r", "requirements.txt", "-r", "requirements/tooling.txt")
if (!$SkipTorch) {
    $dependencyArguments += @("-r", "requirements/onnxruntime-$Cuda.txt", "-c", "requirements/pytorch-$Cuda.txt")
}
& $pythonExe -m pip install @dependencyArguments
Check-Install "Dependency installation"

Write-Output "Install completed"
