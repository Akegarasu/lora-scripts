param(
    [switch]$SkipTorch
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

Write-Output "Installing training dependencies..."
if (!$SkipTorch) {
    & $pythonExe -m pip install torch==2.7.0+cu128 torchvision==0.22.0+cu128 --index-url https://download.pytorch.org/whl/cu128
    Check-Install "PyTorch installation"
    & $pythonExe -m pip install --no-deps xformers==0.0.30 --index-url https://download.pytorch.org/whl/cu128
    Check-Install "xformers installation"
}
& $pythonExe -c "import torch; from packaging.version import Version; assert Version(torch.__version__.split('+')[0]) >= Version('2.6'), 'sd-scripts requires PyTorch >= 2.6'"
Check-Install "PyTorch compatibility check"
& $pythonExe -m pip install --upgrade -r requirements.txt
Check-Install "Dependency installation"

Write-Output "Install completed"
