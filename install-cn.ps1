$Env:HF_HOME = "huggingface"
$Env:PIP_DISABLE_PIP_VERSION_CHECK = 1
$Env:PIP_NO_CACHE_DIR = 1
function InstallFail {
    Write-Output "��װʧ�ܡ�"
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
    Write-Output "���ڴ������⻷��..."
    python -m venv venv
    Check "�������⻷��ʧ�ܣ����� python �Ƿ�װ����Լ� python �汾��"
}

.\venv\Scripts\activate
Check "�������⻷��ʧ�ܡ�"

Write-Output "��װ������������ (�ѽ��й��ڼ��٣����޷�ʹ�ü���Դ���� install.ps1)..."
Set-Location .\sd-scripts
pip install torch==1.13.1+cu117 torchvision==0.14.1+cu117 -f https://mirror.sjtu.edu.cn/pytorch-wheels/torch_stable.html -i https://mirrors.bfsu.edu.cn/pypi/web/simple
Check "torch ��װʧ�ܣ���ɾ�� venv �ļ��к��������С�"
pip install --upgrade -r requirements.txt -i https://mirrors.bfsu.edu.cn/pypi/web/simple
Check "����������װʧ�ܡ�"
#ʹ��xformers0.0.17 �������������ʾ�����ǲ�Ӱ��ʹ�� Error caught was: No module named 'triton'
pip install xformers==0.0.17.dev473 -i https://mirrors.bfsu.edu.cn/pypi/web/simple
Check "xformers ��װʧ�ܡ�"
pip install --upgrade lion-pytorch -i https://mirrors.bfsu.edu.cn/pypi/web/simple
Check "Lion �Ż�����װʧ�ܡ�"
pip install --upgrade lycoris-lora -i https://mirrors.bfsu.edu.cn/pypi/web/simple
Check "lycoris-lora ��װʧ�ܡ�"


Write-Output "��װ bitsandbytes..."
cp .\bitsandbytes_windows\*.dll ..\venv\Lib\site-packages\bitsandbytes\
cp .\bitsandbytes_windows\cextension.py ..\venv\Lib\site-packages\bitsandbytes\cextension.py
cp .\bitsandbytes_windows\main.py ..\venv\Lib\site-packages\bitsandbytes\cuda_setup\main.py

Write-Output "��װ��ϡ�"
Read-Host | Out-Null ;