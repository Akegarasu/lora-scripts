$Env:HF_HOME = "huggingface"

if (!(Test-Path -Path "venv")) {
    Write-Output  "Creating venv for python..."
    python -m venv venv
}
.\venv\Scripts\activate

Write-Output "Installing deps..."
Set-Location .\sd-scripts
pip install torch==1.12.1+cu116 torchvision==0.13.1+cu116 --extra-index-url https://download.pytorch.org/whl/cu116
pip install --upgrade -r requirements.txt
pip install -U -I --no-deps https://github.com/C43H66N12O12S2/stable-diffusion-webui/releases/download/f/xformers-0.0.14.dev0-cp310-cp310-win_amd64.whl

Write-Output "Installing bitsandbytes for windows..."
cp .\bitsandbytes_windows\*.dll ..\venv\Lib\site-packages\bitsandbytes\
cp .\bitsandbytes_windows\cextension.py ..\venv\Lib\site-packages\bitsandbytes\cextension.py
cp .\bitsandbytes_windows\main.py ..\venv\Lib\site-packages\bitsandbytes\cuda_setup\main.py

pip install --upgrade lion-pytorch lycoris-lora

Write-Output "Install completed"
Read-Host | Out-Null ;