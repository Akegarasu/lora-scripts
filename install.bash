echo "Creating python venv..."
python3 -m venv venv
source venv/bin/activate

echo "Installing torch & xformers..."
printf 'Which version of torch do you want to install?
(1) torch 2.0.0+cu118 with xformers 0.0.17 (suggested)
(2) torch 1.12.1+cu116, with xformers 0bad001ddd56c080524d37c84ff58d9cd030ebfd
'
while true; do
    read -p "Choose: " version
    case $version in
    [1]*)
        pip install torch==2.0.0+cu118 torchvision==0.15.1+cu118 --extra-index-url https://download.pytorch.org/whl/cu118
        pip install xformers==0.0.17
        break
        ;;
    [2]*)
        pip install torch==1.12.1+cu116 torchvision==0.13.1+cu116 --extra-index-url https://download.pytorch.org/whl/cu116
        pip install --upgrade git+https://github.com/facebookresearch/xformers.git@0bad001ddd56c080524d37c84ff58d9cd030ebfd
        pip install triton==2.0.0.dev20221202
        break
        ;;
    *) echo "Please enter 1 or 2." ;;
    esac
done

echo "Installing deps..."
cd ./sd-scripts

pip install --upgrade -r requirements.txt
pip install --upgrade lion-pytorch lycoris-lora dadaptation
pip install --upgrade wandb

echo "Install completed"
