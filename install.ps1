$Env:HF_HOME="huggingface"

Write-Output "Creating venv for python..."
python -m venv venv
.\venv\Scripts\activate

Write-Output "Installing deps..."
pip install torch==1.12.1+cu116 torchvision==0.13.1+cu116 --extra-index-url https://download.pytorch.org/whl/cu116
pip install --upgrade -r ./sd-scripts/requirements.txt
pip install -U -I --no-deps https://github.com/C43H66N12O12S2/stable-diffusion-webui/releases/download/f/xformers-0.0.14.dev0-cp310-cp310-win_amd64.whl

Write-Output "Installing bitsandbytes for windows..."
cp .\sd-scripts\bitsandbytes_windows\*.dll .\venv\Lib\site-packages\bitsandbytes\
cp .\sd-scripts\bitsandbytes_windows\cextension.py .\venv\Lib\site-packages\bitsandbytes\cextension.py
cp .\sd-scripts\bitsandbytes_windows\main.py .\venv\Lib\site-packages\bitsandbytes\cuda_setup\main.py