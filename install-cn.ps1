$Env:HF_HOME = "huggingface"
$Env:PIP_DISABLE_PIP_VERSION_CHECK = 1
$Env:PIP_NO_CACHE_DIR = 1
$Env:PIP_INDEX_URL = "https://pypi.tuna.tsinghua.edu.cn/simple"
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
if (Test-Path -Path "python\python.exe") {
    Write-Output "使用 python 文件夹内的 python..."
    $py_path = (Get-Item "python").FullName
    $env:PATH = "$py_path;$env:PATH"
}
else {
    if (!(Test-Path -Path "venv")) {
        Write-Output "正在创建虚拟环境..."
        python -m venv venv
        Check "创建虚拟环境失败，请检查 python 是否安装完毕以及 python 版本是否为64位版本的python 3.10、或python的目录是否在环境变量PATH内。"
    }
    
    Write-Output "检测到虚拟环境，尝试激活..."
    .\venv\Scripts\activate
    Check "激活虚拟环境失败。"
}

Set-Location .\scripts
Write-Output "安装程序所需依赖 (已进行国内加速，若在国外或无法使用加速源请换用 install.ps1 脚本)"
Write-Output "受限于国内加速镜像，torch 安装无法使用镜像源，安装较为缓慢。"
$install_torch = Read-Host "是否需要安装 Torch+xformers? [y/n] (默认为 y)"
if ($install_torch -eq "y" -or $install_torch -eq "Y" -or $install_torch -eq "") {
    python -m pip install torch==2.4.1+cu124 torchvision==0.19.1+cu124 --extra-index-url https://download.pytorch.org/whl/cu124
    Check "torch 安装失败，请删除 venv 文件夹后重新运行。"
    python -m pip install -U -I --no-deps xformers===0.0.28.post1 --extra-index-url https://download.pytorch.org/whl/cu124
    Check "xformers 安装失败。"
}

python -m pip install --upgrade -r requirements.txt
Check "sd-scripts 依赖安装失败。"

Set-Location ..
python -m pip install --upgrade -r requirements.txt
Check "训练界面依赖安装失败。"

Write-Output "安装完毕"
Read-Host | Out-Null ;
