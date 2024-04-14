$Env:HF_HOME = "huggingface"

if (!(Test-Path -Path "venv")) {
    Write-Output  "Creating venv for python..."
    python -m venv venv
}
.\venv\Scripts\activate

Write-Output "Installing deps..."
Set-Location .\sd-scripts
pip install torch==2.2.1+cu118 torchvision==0.17.1+cu118 --extra-index-url https://download.pytorch.org/whl/cu118
pip install -U -I --no-deps xformers==0.0.24+cu118
pip install --upgrade -r requirements.txt

Set-Location ..
pip install --upgrade -r requirements.txt

Write-Output "Install completed"
Read-Host | Out-Null ;