set HF_HOME="huggingface"

echo "正在创建虚拟环境..."
python -m venv venv
.\venv\Scripts\activate.bat

echo "安装程序所需依赖..."
pip install torch==1.12.1+cu116 torchvision==0.13.1+cu116 --extra-index-url https://mirror.sjtu.edu.cn/pytorch-wheels/torch_stable.html
pip install --upgrade -r requirements.txt -i https://mirrors.bfsu.edu.cn/pypi/web/simple
pip install -U -I --no-deps https://jihulab.com/api/v4/projects/82097/packages/pypi/files/4108c84a1bd08244048b6d71005be25aba081839da4fbc801682c5df2bec1c9e/xformers-0.0.14.dev0-cp310-cp310-win_amd64.whl

echo "安装 bitsandbytes..."
cp .\sd-scripts\bitsandbytes_windows\*.dll .\venv\Lib\site-packages\bitsandbytes\
cp .\sd-scripts\bitsandbytes_windows\cextension.py .\venv\Lib\site-packages\bitsandbytes\cextension.py
cp .\sd-scripts\bitsandbytes_windows\main.py .\venv\Lib\site-packages\bitsandbytes\cuda_setup\main.py