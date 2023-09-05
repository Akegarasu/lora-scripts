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

pip install --upgrade -r requirements.txt

Write-Output "Installing bitsandbytes for windows..."
mkdir ..\venv\Lib\site-packages\bitsandbytes\ && mkdir ..\venv\Lib\site-packages\bitsandbytes\cuda_setup\
cp .\bitsandbytes_windows\*.dll ..\venv\Lib\site-packages\bitsandbytes\
cp .\bitsandbytes_windows\cextension.py ..\venv\Lib\site-packages\bitsandbytes\cextension.py
cp .\bitsandbytes_windows\main.py ..\venv\Lib\site-packages\bitsandbytes\cuda_setup\main.py

pip install --upgrade lion-pytorch dadaptation prodigyopt lycoris-lora fastapi uvicorn wandb

Write-Output "Install completed"
Read-Host | Out-Null ;
