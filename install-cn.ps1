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
pip install torch==1.12.1+cu116 torchvision==0.13.1+cu116 -f https://mirror.sjtu.edu.cn/pytorch-wheels/torch_stable.html -i https://mirrors.bfsu.edu.cn/pypi/web/simple
Check "torch ��װʧ�ܣ���ɾ�� venv �ļ��к��������С�"
pip install --upgrade -r requirements.txt -i https://mirrors.bfsu.edu.cn/pypi/web/simple
Check "����������װʧ�ܡ�"
pip install -U -I --no-deps https://jihulab.com/api/v4/projects/82097/packages/pypi/files/e8508fe14c8f2552a822f5e6f5620b24fdd4ba3129c2a31a39b56425bcc023bc/xformers-0.0.14.dev0+torch12-cp310-cp310-win_amd64.whl
Check "xformers ��װʧ�ܡ�"
pip install --upgrade lion-pytorch -i https://mirrors.bfsu.edu.cn/pypi/web/simple
Check "Lion �Ż�����װʧ�ܡ�"
pip install --upgrade locon -i https://mirrors.bfsu.edu.cn/pypi/web/simple
Check "locon ��װʧ�ܡ�"


Write-Output "��װ bitsandbytes..."
cp .\bitsandbytes_windows\*.dll ..\venv\Lib\site-packages\bitsandbytes\
cp .\bitsandbytes_windows\cextension.py ..\venv\Lib\site-packages\bitsandbytes\cextension.py
cp .\bitsandbytes_windows\main.py ..\venv\Lib\site-packages\bitsandbytes\cuda_setup\main.py

Write-Output "��װ��ϡ�"
Read-Host | Out-Null ;