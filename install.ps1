
$Env:HF_HOME = "huggingface"
# 判断 Python 版本是否大于 3.8
$pythonVersion = python --version 2>&1 | % { $_ -match 'Python (\d+\.\d+)' | Out-Null; $Matches[1] }

if ($pythonVersion -gt '3.7') {
    Write-Host "Python version is $pythonVersion, venv has been satisfied ..."

    if (!(Test-Path -Path "venv")) {
        Write-Output  "Creating venv for python..."
        python -m venv venv
    }
    .\venv\Scripts\activate
    
    Write-Output "Installing deps..."
    Set-Location .\sd-scripts
    pip install torch==2.0.0+cu118 torchvision==0.15.1+cu118 --extra-index-url https://download.pytorch.org/whl/cu118
    pip install --upgrade -r requirements.txt
    pip install --upgrade xformers==0.0.17
    
    Write-Output "Installing bitsandbytes for windows..."
    cp .\bitsandbytes_windows\*.dll ..\venv\Lib\site-packages\bitsandbytes\
    cp .\bitsandbytes_windows\cextension.py ..\venv\Lib\site-packages\bitsandbytes\cextension.py
    cp .\bitsandbytes_windows\main.py ..\venv\Lib\site-packages\bitsandbytes\cuda_setup\main.py
    
    pip install --upgrade lion-pytorch lycoris-lora
    
    Write-Output "Install completed"
    Read-Host | Out-Null ;
} else {
    Write-Host "Your Python version is  $pythonVersion and it is TOO LOW ,need >=3.8!!!..."
    Exit 1  # 退出脚本，并返回退出码 1
}



