python3 -m venv venv
source venv/bin/activate

echo "Installing deps..."
cd ./sd-scripts
pip install torch==1.12.1+cu116 torchvision==0.13.1+cu116 --extra-index-url https://download.pytorch.org/whl/cu116
pip install --upgrade -r requirements.txt
pip install git+https://github.com/facebookresearch/xformers.git@0bad001ddd56c080524d37c84ff58d9cd030ebfd
pip install triton==2.0.0.dev20221202
pip install --upgrade lion-pytorch lycoris-lora

echo "Install completed"
