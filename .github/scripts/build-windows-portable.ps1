[CmdletBinding()]
param(
    [string]$OutputDirectory,
    [ValidatePattern('^\d+\.\d+\.\d+$')]
    [string]$PythonVersion = "3.11.9"
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

function Assert-NativeSuccess([string]$Step) {
    if ($LASTEXITCODE -ne 0) {
        throw "$Step failed (exit code $LASTEXITCODE)."
    }
}

function Remove-BuildPath([string]$Path, [string]$Root) {
    $target = [IO.Path]::GetFullPath($Path)
    $rootPrefix = [IO.Path]::GetFullPath($Root).TrimEnd('\') + '\'
    if (!$target.StartsWith($rootPrefix, [StringComparison]::OrdinalIgnoreCase)) {
        throw "Refusing to remove a path outside the build directory: $target"
    }
    if (Test-Path -LiteralPath $target) {
        Remove-Item -LiteralPath $target -Recurse -Force
    }
}

if ($env:OS -ne "Windows_NT") {
    throw "This builder requires Windows x64."
}
$repositoryRoot = (Resolve-Path (Join-Path $PSScriptRoot "../..")).Path
$frontendDist = Join-Path $repositoryRoot "frontend/dist"
foreach ($file in @("index.html", "build-info.json")) {
    if (!(Test-Path -LiteralPath (Join-Path $frontendDist $file) -PathType Leaf)) {
        throw "Build and validate frontend/dist before creating the portable package (missing $file)."
    }
}

$hostPython = (Get-Command python -CommandType Application -ErrorAction Stop).Source
$pythonRelease = [version]$PythonVersion
$expectedMinor = "$($pythonRelease.Major).$($pythonRelease.Minor)"
$hostMinor = & $hostPython -c "import struct, sys; assert struct.calcsize('P') == 8; print(f'{sys.version_info.major}.{sys.version_info.minor}')"
Assert-NativeSuccess "Host Python check"
if ($hostMinor.Trim() -ne $expectedMinor) {
    throw "The full host Python must be $expectedMinor x64 to build compatible wheels."
}
$sevenZip = (Get-Command 7z -CommandType Application -ErrorAction Stop).Source

if (!$OutputDirectory) {
    $temporaryBase = if ($env:RUNNER_TEMP) { $env:RUNNER_TEMP } else { [IO.Path]::GetTempPath() }
    $OutputDirectory = Join-Path $temporaryBase "lora-scripts-portable-$([guid]::NewGuid().ToString('N'))"
}
$OutputDirectory = [IO.Path]::GetFullPath($OutputDirectory)
New-Item -ItemType Directory -Path $OutputDirectory -Force | Out-Null
$archivePath = Join-Path $OutputDirectory "lora-scripts_windows_portable_nvidia.7z"
$checksumPath = "$archivePath.sha256"
foreach ($path in @($archivePath, $checksumPath)) {
    if (Test-Path -LiteralPath $path) {
        throw "Output already exists: $path. Use a fresh output directory."
    }
}

# A fresh staging directory ensures local models, environments and user data
# cannot enter the package and that retries never delete an earlier build.
$workRoot = Join-Path $OutputDirectory "work-$([guid]::NewGuid().ToString('N'))"
$stageRoot = Join-Path $workRoot "lora-scripts_windows_portable"
$wheelhouse = Join-Path $workRoot "wheelhouse"
New-Item -ItemType Directory -Path $stageRoot, $wheelhouse | Out-Null
$sourceArchive = Join-Path $workRoot "source.tar"
& git -C $repositoryRoot archive --format=tar "--output=$sourceArchive" HEAD
Assert-NativeSuccess "Source export"
& tar -xf $sourceArchive -C $stageRoot
Assert-NativeSuccess "Source extraction"

foreach ($relativePath in @(".github", ".agents", ".vscode", "frontend-old", "frontend")) {
    Remove-BuildPath -Path (Join-Path $stageRoot $relativePath) -Root $stageRoot
}
New-Item -ItemType Directory -Path (Join-Path $stageRoot "frontend") | Out-Null
Copy-Item -LiteralPath $frontendDist -Destination (Join-Path $stageRoot "frontend/dist") -Recurse
Copy-Item -LiteralPath (Join-Path $repositoryRoot ".github/portable/run_gui.bat") -Destination $stageRoot
Copy-Item -LiteralPath (Join-Path $repositoryRoot ".github/portable/README.txt") -Destination (Join-Path $stageRoot "README-portable.txt")
foreach ($directory in @("config", "models", "train", "output", "logs", "huggingface")) {
    New-Item -ItemType Directory -Path (Join-Path $stageRoot $directory) -Force | Out-Null
}

$embeddedArchive = Join-Path $workRoot "python-$PythonVersion-embed-amd64.zip"
Invoke-WebRequest -Uri "https://www.python.org/ftp/python/$PythonVersion/python-$PythonVersion-embed-amd64.zip" -OutFile $embeddedArchive
$pythonRoot = Join-Path $stageRoot "python"
Expand-Archive -LiteralPath $embeddedArchive -DestinationPath $pythonRoot
$embeddedPython = Join-Path $pythonRoot "python.exe"
# Restore ordinary script-directory imports so sd-scripts can find its own
# 'library' package when Accelerate launches the training entrypoint.
$isolatedPath = Join-Path $pythonRoot "python$($pythonRelease.Major)$($pythonRelease.Minor)._pth"
Remove-Item -LiteralPath $isolatedPath

$rootRequirements = Join-Path $stageRoot "requirements.txt"
$portableRequirements = Join-Path $repositoryRoot ".github/portable/requirements.txt"
& $hostPython -m pip wheel --wheel-dir $wheelhouse --prefer-binary --no-cache-dir `
    --extra-index-url https://download.pytorch.org/whl/cu128 `
    -r $rootRequirements -r $portableRequirements
Assert-NativeSuccess "Dependency wheel build"
# The full interpreter builds any source-only wheels; the embedded runtime
# receives only wheel installs, including its own pip and setuptools.
& $hostPython -m pip --python $embeddedPython install --no-index --find-links $wheelhouse --no-compile --ignore-installed `
    -r $rootRequirements -r $portableRequirements
Assert-NativeSuccess "Portable dependency installation"
Remove-BuildPath -Path $wheelhouse -Root $workRoot
# Like ComfyUI, omit these large static build libraries from the runtime
# distribution. Keep all runtime DLLs and the other extension import libraries.
foreach ($library in @("dnnl.lib", "libprotoc.lib", "libprotobuf.lib")) {
    Remove-BuildPath -Path (Join-Path $pythonRoot "Lib/site-packages/torch/lib/$library") -Root $stageRoot
}

# Removing _pth restores script imports, but Windows registry paths can still
# leak into sys.path. Pin this runtime's home just as run_gui.bat does, and
# restore the host environment before invoking the separate smoke test driver.
$savedEnvironment = @{}
foreach ($name in @("PYTHONHOME", "PYTHONPATH", "PYTHONSAFEPATH", "PYTHONUTF8", "PYTHONDONTWRITEBYTECODE")) {
    $savedEnvironment[$name] = [Environment]::GetEnvironmentVariable($name, "Process")
}
try {
    $env:PYTHONHOME = $pythonRoot
    $env:PYTHONPATH = ""
    $env:PYTHONSAFEPATH = ""
    $env:PYTHONUTF8 = "1"
    $env:PYTHONDONTWRITEBYTECODE = "1"
    & $embeddedPython -s -m pip check
    Assert-NativeSuccess "Portable dependency consistency check"
    & $embeddedPython -s -c "import platform, torch, torchvision, xformers, bitsandbytes, onnxruntime; assert platform.python_version() == '$PythonVersion'; assert torch.version.cuda == '12.8'; print('Portable Python and NVIDIA runtime imports passed')"
    Assert-NativeSuccess "Portable runtime imports"
    & $embeddedPython -s -m pip freeze --all | Set-Content -LiteralPath (Join-Path $stageRoot "installed-packages.txt") -Encoding utf8
    Assert-NativeSuccess "Installed package manifest"
} finally {
    foreach ($name in $savedEnvironment.Keys) {
        [Environment]::SetEnvironmentVariable($name, $savedEnvironment[$name], "Process")
    }
}

& $hostPython (Join-Path $repositoryRoot ".github/scripts/smoke_windows_portable.py") $stageRoot
Assert-NativeSuccess "Portable application smoke test"

Push-Location $workRoot
try {
    & $sevenZip a -t7z -m0=lzma2 -mx=9 -mfb=128 -md=256m -ms=on -mf=BCJ2 -mmt=2 `
        '-xr!__pycache__' '-xr!*.pyc' $archivePath "lora-scripts_windows_portable"
    Assert-NativeSuccess "Portable archive creation"
} finally {
    Pop-Location
}
& $sevenZip t $archivePath
Assert-NativeSuccess "Portable archive integrity check"
if ((Get-Item -LiteralPath $archivePath).Length -ge 2GB) {
    throw "The portable archive exceeds GitHub's 2 GiB release asset limit."
}
$digest = (Get-FileHash -LiteralPath $archivePath -Algorithm SHA256).Hash.ToLowerInvariant()
"$digest  $([IO.Path]::GetFileName($archivePath))" | Set-Content -LiteralPath $checksumPath -Encoding ascii
Write-Host "Portable release asset: $archivePath"
