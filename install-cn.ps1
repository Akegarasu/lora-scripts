$Env:HF_HOME = "huggingface"
$Env:PIP_DISABLE_PIP_VERSION_CHECK = 1
$Env:PIP_NO_CACHE_DIR = 1
$Env:PIP_INDEX_URL = "https://pypi.tuna.tsinghua.edu.cn/simple"
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
if (Test-Path -Path "python\python.exe") {
    Write-Output "ʹ�� python �ļ����ڵ� python..."
    $py_path = (Get-Item "python").FullName
    $env:PATH = "$py_path;$env:PATH"
}
else {
    if (!(Test-Path -Path "venv")) {
        Write-Output "���ڴ������⻷��..."
        python -m venv venv
        Check "�������⻷��ʧ�ܣ����� python �Ƿ�װ����Լ� python �汾�Ƿ�Ϊ64λ�汾��python 3.10����python��Ŀ¼�Ƿ��ڻ�������PATH�ڡ�"
    }
    
    Write-Output "��⵽���⻷�������Լ���..."
    .\venv\Scripts\activate
    Check "�������⻷��ʧ�ܡ�"
}

Write-Output "��װ������������ (�ѽ��й��ڼ��٣����ڹ�����޷�ʹ�ü���Դ�뻻�� install.ps1 �ű�)"
Write-Output "�����ڹ��ڼ��پ���torch ��װ�޷�ʹ�þ���Դ����װ��Ϊ������"
$install_torch = Read-Host "�Ƿ���Ҫ��װ Torch+xformers? [y/n] (Ĭ��Ϊ y)"
if ($install_torch -eq "y" -or $install_torch -eq "Y" -or $install_torch -eq "") {
    python -m pip install torch==2.4.1+cu124 torchvision==0.19.1+cu124 --extra-index-url https://download.pytorch.org/whl/cu124
    Check "torch ��װʧ�ܣ���ɾ�� venv �ļ��к��������С�"
    python -m pip install -U -I --no-deps xformers===0.0.28.post1 --extra-index-url https://download.pytorch.org/whl/cu124
    Check "xformers ��װʧ�ܡ�"
}

python -m pip install --upgrade -r requirements.txt
Check "ѵ������������װʧ�ܡ�"

Write-Output "��װ���"
Read-Host | Out-Null ;
