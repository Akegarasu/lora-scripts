$Env:HF_HOME = "huggingface"

if (!(Test-Path -Path "venv")) {
    Write-Output  "Creating venv for python..."
    python -m venv venv
}
.\venv\Scripts\activate

Write-Output "Installing deps..."
Set-Location .\sd-scripts
pip install torch==2.0.0+cu118 torchvision==0.15.1+cu118 --extra-index-url https://download.pytorch.org/whl/cu118
pip install -U -I --no-deps xformers==0.0.19

Write-Output "Installing bitsandbytes for windows..."
pip install bitsandbytes==0.41.1 --index-url https://jllllll.github.io/bitsandbytes-windows-webui

pip install --upgrade -r requirements.txt

Set-Location ..
pip install --upgrade -r requirements_win.txt

Write-Output "Install completed"
Read-Host | Out-Null ;