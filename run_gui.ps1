param(
  [Parameter(Mandatory=$false)]
  [string]$hostname = "127.0.0.1",

  [Parameter(Mandatory=$false)]
  [string]$port = "28000"
)

.\venv\Scripts\activate

$Env:HF_HOME = "huggingface"
$Env:PYTHONUTF8 = "1"

python gui.py $hostname $port
