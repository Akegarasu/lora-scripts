$Env:HF_HOME = "huggingface"

if (!(Test-Path -Path "venv")) {
    Write-Output  "Creating venv for python..."
    python -m venv venv
}
.\venv\Scripts\activate

Write-Output "Installing deps..."
Set-Location .\scripts
pip install torch==2.4.0 torchvision==0.19.0 --extra-index-url https://download.pytorch.org/whl/cu121
pip install -U -I --no-deps xformers==0.0.27.post2
pip install --upgrade -r requirements.txt

Set-Location ..
pip install --upgrade -r requirements.txt

Write-Output "Install completed"
Read-Host | Out-Null ;