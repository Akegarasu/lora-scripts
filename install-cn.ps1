$Env:HF_HOME = "huggingface"
$Env:PIP_DISABLE_PIP_VERSION_CHECK = 1
$Env:PIP_NO_CACHE_DIR = 1
function InstallFail {
    Write-Output "安装失败。"
    Read-Host | Out-Null ;
    Exit
}

function Check {
    param (
        $ErrorInfo
    )
    if (!($?)) {
        Write-Output $ErrorInfo
        InstallFail
    }
}

if (!(Test-Path -Path "venv")) {
    Write-Output "正在创建虚拟环境..."
    python -m venv venv
    Check "创建虚拟环境失败，请检查 python 是否安装完毕以及 python 版本。"
}

.\venv\Scripts\activate
Check "激活虚拟环境失败。"

Write-Output "安装程序所需依赖 (已进行国内加速，若无法使用加速源请用 install.ps1)..."
Set-Location .\sd-scripts
pip install torch==2.0.0+cu118 torchvision==0.15.1+cu118 -f https://mirror.sjtu.edu.cn/pytorch-wheels/torch_stable.html -i https://mirrors.bfsu.edu.cn/pypi/web/simple
Check "torch 安装失败，请删除 venv 文件夹后重新运行。"
pip install --upgrade -r requirements.txt -i https://mirrors.bfsu.edu.cn/pypi/web/simple
Check "其他依赖安装失败。"
pip install -U -I --no-deps xformers==0.0.17rc482 -i https://mirrors.aliyun.com/pypi/simple/
Check "xformers 安装失败。"
pip install --upgrade lion-pytorch -i https://mirrors.bfsu.edu.cn/pypi/web/simple
Check "Lion 优化器安装失败。"
pip install --upgrade lycoris-lora -i https://mirrors.bfsu.edu.cn/pypi/web/simple
Check "lycoris 安装失败。"


Write-Output "安装 bitsandbytes..."
cp .\bitsandbytes_windows\*.dll ..\venv\Lib\site-packages\bitsandbytes\
cp .\bitsandbytes_windows\cextension.py ..\venv\Lib\site-packages\bitsandbytes\cextension.py
cp .\bitsandbytes_windows\main.py ..\venv\Lib\site-packages\bitsandbytes\cuda_setup\main.py

Write-Output "安装完毕"
Read-Host | Out-Null ;
