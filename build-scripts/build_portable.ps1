param(
    [string]$ProjectRoot = (Split-Path $PSScriptRoot -Parent),
    [string]$Version     = "2.5.0",
    [string]$PythonVer   = "3.10.11",
    [string]$TkinterSourceRoot = "",
    [switch]$Clean,
    [switch]$Skip7z,
    [switch]$SkipTaggerPrefetch,
    [string]$TaggerCacheSource = ""
)

$ErrorActionPreference = "Stop"
$startTime = Get-Date

$buildDir    = Join-Path $ProjectRoot "build"
$portableDir = Join-Path $buildDir "SD-Trainer-Portable"
$pythonDir   = Join-Path $portableDir "python_embeded"
$sdtDir      = Join-Path $portableDir "SD-Trainer"
$tempGitCloneDir = Join-Path $buildDir "_portable_git_metadata"

$7zExe = "C:\Program Files\7-Zip\7z.exe"
if (-not (Test-Path $7zExe)) {
    $found = Get-Command 7z -ErrorAction SilentlyContinue
    if ($found) { $7zExe = $found.Source } else { $7zExe = $null }
}

Write-Host ""
Write-Host "  SD-Trainer Portable Package Builder  v$Version" -ForegroundColor Cyan
Write-Host ""

& (Join-Path $ProjectRoot "build-scripts\00-build-frontend.ps1") -ProjectRoot $ProjectRoot
if ($LASTEXITCODE -ne 0) { throw "Frontend build failed" }

# ---- Clean ----

if ($Clean -and (Test-Path $portableDir)) {
    Write-Host "[Clean] Removing old build..." -ForegroundColor Yellow
    Remove-Item $portableDir -Recurse -Force
}
New-Item -ItemType Directory -Path $portableDir -Force | Out-Null

function Copy-PortableBatchFile {
    param(
        [Parameter(Mandatory = $true)][string]$Source,
        [Parameter(Mandatory = $true)][string]$Destination
    )
    if (-not (Test-Path $Source)) {
        throw "Batch source not found: $Source"
    }
    $dir = Split-Path $Destination -Parent
    if ($dir -and -not (Test-Path $dir)) {
        New-Item -ItemType Directory -Path $dir -Force | Out-Null
    }
    $text = [System.IO.File]::ReadAllText($Source)
    $text = $text -replace "`r`n", "`n" -replace "`r", "`n" -replace "`n", "`r`n"
    if ($text.Length -gt 0 -and [int][char]$text[0] -eq 0xFEFF) {
        $text = $text.Substring(1)
    }
    [System.IO.File]::WriteAllText($Destination, $text, (New-Object System.Text.UTF8Encoding $false))
}

function Normalize-PortableBatchFilesInTree {
    param([Parameter(Mandatory = $true)][string]$Root)
    Get-ChildItem -Path $Root -Filter "*.bat" -Recurse -File | ForEach-Object {
        Copy-PortableBatchFile -Source $_.FullName -Destination $_.FullName
    }
}

function Invoke-GitChecked {
    param(
        [string[]]$Arguments,
        [string]$WorkingDirectory = $ProjectRoot,
        [string]$ErrorMessage = "git command failed"
    )
    & git -C $WorkingDirectory @Arguments
    if ($LASTEXITCODE -ne 0) {
        throw $ErrorMessage
    }
}

function Initialize-DatasetTagEditor {
    Write-Host "  Checking dataset-tag-editor submodule..."
    $tagEditorLaunch = Join-Path $ProjectRoot "mikazuki\dataset-tag-editor\scripts\launch.py"
    if (-not (Test-Path $tagEditorLaunch)) {
        Write-Host "  Initializing dataset-tag-editor submodule..."
        Invoke-GitChecked `
            -Arguments @("submodule", "update", "--init", "--recursive", "--depth=1", "--", "mikazuki/dataset-tag-editor") `
            -ErrorMessage "dataset-tag-editor submodule init failed"
    }
    if (-not (Test-Path $tagEditorLaunch)) {
        throw "dataset-tag-editor\scripts\launch.py missing after submodule init"
    }
}

function Clone-SDTrainerGitMetadata {
    param([string]$Destination)
    Write-Host "  Embedding shallow .git metadata for Update-SD-Trainer.bat..."
    if (Test-Path $tempGitCloneDir) {
        Remove-Item $tempGitCloneDir -Recurse -Force
    }
    $branch = (& git -C $ProjectRoot branch --show-current 2>$null | Select-Object -First 1)
    if (-not $branch) { $branch = "main" }
    $remote = (& git -C $ProjectRoot remote get-url origin 2>$null | Select-Object -First 1)
    if (-not $remote) { $remote = "https://github.com/wochenlong/lora-scripts-next.git" }

    & git clone --depth=1 --single-branch --branch $branch $remote $tempGitCloneDir
    if ($LASTEXITCODE -ne 0) {
        throw "failed to clone shallow git metadata from $remote"
    }
    $dstGit = Join-Path $Destination "SD-Trainer\.git"
    if (Test-Path $dstGit) {
        Remove-Item $dstGit -Recurse -Force
    }
    Copy-Item (Join-Path $tempGitCloneDir ".git") $dstGit -Recurse -Force
    Remove-Item $tempGitCloneDir -Recurse -Force

    if (-not (Test-Path (Join-Path $dstGit "HEAD"))) {
        throw "embedded SD-Trainer\.git is missing HEAD"
    }
}

function Write-PortableBuildMetadata {
    param(
        [string]$TrainerDir,
        [string]$Version
    )
    $sha = (& git -C $ProjectRoot rev-parse --short HEAD 2>$null | Select-Object -First 1)
    if ($sha) { $sha = $sha.Trim() } else { $sha = "unknown" }
    $utc = (Get-Date).ToUniversalTime().ToString("yyyy-MM-ddTHH:mm:ssZ")
    $path = Join-Path $TrainerDir "PORTABLE_BUILD"
    @(
        $sha
        "built_at=$utc"
        "version=$Version"
    ) | Set-Content $path -Encoding UTF8
    Write-Host "  Wrote PORTABLE_BUILD ($sha)"
}

function Resolve-TaggerCacheSource {
    param(
        [string]$Explicit,
        [string]$BuildDirectory
    )
    if ($Explicit -and (Test-Path $Explicit)) {
        return (Resolve-Path $Explicit).Path
    }
    $modelDirName = "models--SmilingWolf--wd-v1-4-convnextv2-tagger-v2"
    $candidates = @()
    foreach ($dir in Get-ChildItem $BuildDirectory -Directory -ErrorAction SilentlyContinue) {
        if ($dir.Name -notlike "SD-Trainer*") { continue }
        $hubModel = Join-Path $dir.FullName "huggingface\hub\$modelDirName"
        if (Test-Path $hubModel) {
            $candidates += $dir.FullName
        }
    }
    if ($candidates.Count -eq 0) { return $null }
    return ($candidates | Sort-Object { $_ } -Descending | Select-Object -First 1)
}

function Copy-TaggerCacheFromSource {
    param(
        [string]$SourceRoot,
        [string]$DestinationPortable
    )
    $modelDirName = "models--SmilingWolf--wd-v1-4-convnextv2-tagger-v2"
    $copied = $false

    $srcHubModel = Join-Path $SourceRoot "huggingface\hub\$modelDirName"
    $dstHub = Join-Path $DestinationPortable "huggingface\hub"
    if (Test-Path $srcHubModel) {
        New-Item -ItemType Directory -Path $dstHub -Force | Out-Null
        $null = robocopy $srcHubModel (Join-Path $dstHub $modelDirName) /E /NFL /NDL /NJH /NJS /NC /NS
        if ($LASTEXITCODE -le 7) { $copied = $true }
    }

    $srcWd14 = Join-Path $SourceRoot "tagger-models\wd14"
    $dstWd14 = Join-Path $DestinationPortable "tagger-models\wd14"
    if (Test-Path $srcWd14) {
        New-Item -ItemType Directory -Path $dstWd14 -Force | Out-Null
        $null = robocopy $srcWd14 $dstWd14 /E /NFL /NDL /NJH /NJS /NC /NS
        if ($LASTEXITCODE -le 7) { $copied = $true }
    }

    return $copied
}

# ==== Step 1: Python Embeddable ====

Write-Host "[1/6] Preparing Python $PythonVer Embeddable..." -ForegroundColor Cyan

$pythonZipName = "python-$PythonVer-embed-amd64.zip"
$pythonUrl     = "https://www.python.org/ftp/python/$PythonVer/$pythonZipName"
$pythonZipPath = Join-Path $env:TEMP $pythonZipName
$pythonExe     = Join-Path $pythonDir "python.exe"

if (Test-Path $pythonExe) {
    Write-Host "  Python already exists, skip" -ForegroundColor Green
} else {
    New-Item -ItemType Directory -Path $pythonDir -Force | Out-Null
    if (-not (Test-Path $pythonZipPath)) {
        Write-Host "  Downloading $pythonZipName ..."
        Invoke-WebRequest -Uri $pythonUrl -OutFile $pythonZipPath -UseBasicParsing
    }
    Write-Host "  Extracting..."
    Expand-Archive -Path $pythonZipPath -DestinationPath $pythonDir -Force
    Write-Host "  Done" -ForegroundColor Green
}

# python310._pth (include Lib/ so bundled tkinter is importable)
$pthLines = @(
    "../SD-Trainer",
    "../SD-Trainer/vendor/sd-scripts",
    "python310.zip",
    "Lib",
    "Lib/site-packages",
    ".",
    "import site"
)
$pthFile = Join-Path $pythonDir "python310._pth"
[System.IO.File]::WriteAllLines($pthFile, $pthLines)
Write-Host "  Created python310._pth"

# Lib/site-packages
$sitePackages = Join-Path $pythonDir "Lib\site-packages"
New-Item -ItemType Directory -Path $sitePackages -Force | Out-Null

# tkinter for GUI folder/file picker (embeddable Python omits it by default)
function Test-TkinterSourceRoot {
    param([string]$Root)
    if (-not $Root -or -not (Test-Path $Root)) { return $false }
    $libTk = Join-Path $Root "Lib\tkinter"
    if (-not (Test-Path $libTk)) { $libTk = Join-Path $Root "lib\tkinter" }
    $tcl = Join-Path $Root "tcl"
    $pyd = Join-Path $Root "DLLs\_tkinter.pyd"
    return (Test-Path $libTk) -and (Test-Path $tcl) -and (Test-Path $pyd)
}

function Get-TkinterSourceCandidates {
    param([string]$ExpectedVersion = "3.10")
    $roots = [System.Collections.Generic.List[string]]::new()

    if ($TkinterSourceRoot -and (Test-Path $TkinterSourceRoot)) {
        $roots.Add($TkinterSourceRoot.TrimEnd('\'))
    }
    if ($env:SD_TRAINER_TKINTER_SOURCE -and (Test-Path $env:SD_TRAINER_TKINTER_SOURCE)) {
        $roots.Add($env:SD_TRAINER_TKINTER_SOURCE.TrimEnd('\'))
    }

    # Official CPython first — avoid conda/mambaforge (often missing tcl/)
    foreach ($fixed in @(
        "C:\Program Files\Python310",
        "C:\Program Files (x86)\Python310"
    )) {
        if (Test-Path $fixed) { $roots.Add($fixed) }
    }

    foreach ($exe in @(
        "C:\Program Files\Python310\python.exe",
        "C:\Program Files (x86)\Python310\python.exe"
    )) {
        if (-not (Test-Path $exe)) { continue }
        try {
            $out = (& $exe -c "import sys; print(sys.base_prefix)" 2>$null | Select-Object -First 1)
            if ($out) { $roots.Add($out.Trim()) }
        } catch { }
    }

    try {
        $pyList = & py -0p 2>&1
        foreach ($line in $pyList) {
            if ($line -notmatch "3\.10") { continue }
            if ($line -notmatch "([A-Za-z]:\\[^\s]+\.exe)\s*$") { continue }
            $exe = $Matches[1].Trim()
            if ($exe -match "mambaforge|miniconda|anaconda|conda", "IgnoreCase") { continue }
            $out = (& $exe -c "import sys; print(sys.base_prefix)" 2>$null | Select-Object -First 1)
            if ($out) { $roots.Add($out.Trim()) }
        }
    } catch { }

    return $roots | Select-Object -Unique
}

function Install-EmbeddedTkinter {
    param(
        [string]$EmbedDir,
        [string]$ExpectedVersion = "3.10"
    )
    $fullRoot = $null
    foreach ($candidate in (Get-TkinterSourceCandidates -ExpectedVersion $ExpectedVersion)) {
        if (Test-TkinterSourceRoot $candidate) {
            $fullRoot = $candidate
            break
        }
    }
    if (-not $fullRoot) {
        Write-Host "  ERROR: No CPython $ExpectedVersion with tcl/ + tkinter found." -ForegroundColor Red
        Write-Host "         Install https://www.python.org/downloads/release/python-31011/ (Windows x64)," -ForegroundColor Red
        Write-Host "         or pass -TkinterSourceRoot 'C:\Program Files\Python310'," -ForegroundColor Red
        Write-Host "         or set env SD_TRAINER_TKINTER_SOURCE to a full Python root." -ForegroundColor Red
        Write-Host "         Do NOT use conda/mambaforge — folder picker will break." -ForegroundColor Red
        throw "tkinter source not found"
    }
    $libTk = Join-Path $fullRoot "Lib\tkinter"
    if (-not (Test-Path $libTk)) {
        $libTk = Join-Path $fullRoot "lib\tkinter"
    }
    $dllDir = Join-Path $fullRoot "DLLs"
    if (-not (Test-Path $libTk) -or -not (Test-Path $dllDir)) {
        Write-Host "  WARNING: tkinter/tcl files missing under $fullRoot" -ForegroundColor Yellow
        return
    }
    $embedLib = Join-Path $EmbedDir "Lib"
    New-Item -ItemType Directory -Path $embedLib -Force | Out-Null
    Copy-Item $libTk (Join-Path $embedLib "tkinter") -Recurse -Force
    $tclSrc = Join-Path $fullRoot "tcl"
    if (Test-Path $tclSrc) {
        Copy-Item $tclSrc (Join-Path $EmbedDir "tcl") -Recurse -Force
    } else {
        Write-Host "  WARNING: tcl directory not found at $tclSrc (tkinter may still work)" -ForegroundColor Yellow
    }
    foreach ($name in @("_tkinter.pyd", "tcl86t.dll", "tk86t.dll")) {
        $src = Join-Path $dllDir $name
        if (Test-Path $src) {
            Copy-Item $src (Join-Path $EmbedDir $name) -Force
        }
    }
    $oldEAP2 = $ErrorActionPreference; $ErrorActionPreference = "Continue"
    $check = & (Join-Path $EmbedDir "python.exe") -c "import tkinter; print('ok')" 2>&1
    $ErrorActionPreference = $oldEAP2
    if ($LASTEXITCODE -eq 0 -and ($check -match "ok")) {
        Write-Host "  tkinter bundled from $fullRoot" -ForegroundColor Green
    } else {
        Write-Host "  ERROR: tkinter verification failed after copy from $fullRoot" -ForegroundColor Red
        Write-Host "         $check" -ForegroundColor Red
        throw "tkinter bundle verification failed"
    }
}

# Skip tkinter install if already present and working
$oldEAP = $ErrorActionPreference; $ErrorActionPreference = "Continue"
$tkCheck = & $pythonExe -s -c "import tkinter; print('ok')" 2>&1
$ErrorActionPreference = $oldEAP
if ($LASTEXITCODE -eq 0 -and ($tkCheck -match "ok")) {
    Write-Host "  tkinter already bundled, skip" -ForegroundColor Green
} else {
    Install-EmbeddedTkinter -EmbedDir $pythonDir -ExpectedVersion "3.10"
}

# get-pip.py
$getPipPath = Join-Path $pythonDir "get-pip.py"
if (-not (Test-Path $getPipPath)) {
    Write-Host "  Downloading get-pip.py..."
    Invoke-WebRequest -Uri "https://bootstrap.pypa.io/get-pip.py" -OutFile $getPipPath -UseBasicParsing
}

# ==== Step 2: Copy project files ====

Write-Host ""
Write-Host "[2/6] Copying project files..." -ForegroundColor Cyan

Initialize-DatasetTagEditor

$copyDirs = @(
    @{ Src = "assets";  Dst = "assets" },
    @{ Src = "mikazuki"; Dst = "mikazuki" },
    @{ Src = "frontend"; Dst = "frontend" },
    @{ Src = "config";   Dst = "config" },
    @{ Src = "scripts";  Dst = "scripts" },
    @{ Src = "vendor";   Dst = "vendor" },
    @{ Src = "train_monitor"; Dst = "train_monitor" }
)

$copyFiles = @(
    "gui.py",
    "run_gui.bat",
    "requirements.txt",
    "setup_environment.py",
    "VERSION",
    "LICENSE",
    "NOTICE.md",
    "CHANGELOG.md",
    "README.md",
    "README-zh.md"
)

$excludeDirs = @(
    ".git", "__pycache__", ".vscode", ".idea",
    "node_modules", ".sisyphus", ".playwright-mcp", ".tmp",
    "anima_lora", "extensions", "drafts"
)

foreach ($dir in $copyDirs) {
    $src = Join-Path $ProjectRoot $dir.Src
    $dst = Join-Path $sdtDir $dir.Dst
    if (Test-Path $src) {
        $xdArgs = @()
        foreach ($xd in $excludeDirs) { $xdArgs += "/XD"; $xdArgs += $xd }
        $null = robocopy $src $dst /E /NFL /NDL /NJH /NJS /NC /NS $xdArgs
        Write-Host "  Copied $($dir.Src)/"
    } else {
        Write-Host "  [skip] $($dir.Src)/ not found" -ForegroundColor Yellow
    }
}

# robocopy /XD can miss nested git metadata or local test directories when
# names are matched relative to the copied subtree, so run a deterministic
# cleanup pass before archiving.
foreach ($exclude in $excludeDirs) {
    Get-ChildItem -Path $sdtDir -Force -Recurse -ErrorAction SilentlyContinue |
        Where-Object { $_.Name -eq $exclude } |
        Sort-Object FullName -Descending |
        ForEach-Object {
            Remove-Item $_.FullName -Recurse -Force -ErrorAction SilentlyContinue
        }
}

New-Item -ItemType Directory -Path $sdtDir -Force | Out-Null
foreach ($file in $copyFiles) {
    $src = Join-Path $ProjectRoot $file
    if (Test-Path $src) {
        Copy-Item $src -Destination (Join-Path $sdtDir $file)
    }
}
Clone-SDTrainerGitMetadata -Destination $portableDir
Write-PortableBuildMetadata -TrainerDir $sdtDir -Version $Version
Write-Host "  Copied root files"
Write-Host "  Done" -ForegroundColor Green

# ==== Step 3: Bundle default WD tagger (offline batch tagging) ====

Write-Host ""
Write-Host "[3/6] Bundling default WD tagger (wd14-convnextv2-v2, ~388 MB)..." -ForegroundColor Cyan

$hfHome = Join-Path $portableDir "huggingface"
$taggerModelsDir = Join-Path $portableDir "tagger-models"
New-Item -ItemType Directory -Path $hfHome -Force | Out-Null
New-Item -ItemType Directory -Path $taggerModelsDir -Force | Out-Null
New-Item -ItemType Directory -Path (Join-Path $portableDir "tagger-models\wd14") -Force | Out-Null
New-Item -ItemType Directory -Path (Join-Path $portableDir "tagger-models\vlm") -Force | Out-Null
$prefetchScript = Join-Path $sdtDir "scripts\prefetch_default_tagger.py"
$taggerCacheSrc = Resolve-TaggerCacheSource -Explicit $TaggerCacheSource -BuildDirectory $buildDir
if ($taggerCacheSrc) {
    Write-Host "  Seeding tagger cache from: $taggerCacheSrc"
    if (-not (Copy-TaggerCacheFromSource -SourceRoot $taggerCacheSrc -DestinationPortable $portableDir)) {
        Write-Host "  WARNING: tagger cache source had no usable hub/tagger-models data" -ForegroundColor Yellow
    }
}

if ($SkipTaggerPrefetch) {
    Write-Host "  Skipping tagger prefetch (-SkipTaggerPrefetch)" -ForegroundColor Yellow
} elseif (-not (Test-Path $prefetchScript)) {
    throw "prefetch script missing: $prefetchScript"
} else {
    $env:HF_HOME = $hfHome
    $env:MIKAZUKI_TAGGER_MODELS_DIR = $taggerModelsDir
    if (-not $env:HF_ENDPOINT) { $env:HF_ENDPOINT = "https://hf-mirror.com" }

    $prefetchPython = $null
    if (Test-Path $pythonExe) {
        $prefetchPython = $pythonExe
    } elseif (Test-Path (Join-Path $ProjectRoot "venv\Scripts\python.exe")) {
        $prefetchPython = (Join-Path $ProjectRoot "venv\Scripts\python.exe")
    } elseif (Get-Command python -ErrorAction SilentlyContinue) {
        $prefetchPython = (Get-Command python).Source
    }

    if (-not $prefetchPython) {
        throw "No Python available for tagger prefetch (need embed python, venv, or PATH python)"
    }

    Write-Host "  Prefetch Python: $prefetchPython"

    $prevEap = $ErrorActionPreference
    $ErrorActionPreference = 'Continue'
    if ($prefetchPython -eq $pythonExe) {
        if (Test-Path $getPipPath) {
            Write-Host "  Bootstrapping pip in embedded Python..."
            & $pythonExe $getPipPath --no-warn-script-location 2>&1 | Out-Null
        }
        & $prefetchPython -s -m pip install -q huggingface_hub requests 2>&1 | Out-Null
        & $prefetchPython -s $prefetchScript --hf-home $hfHome --tagger-models-dir $taggerModelsDir --if-missing
    } else {
        & $prefetchPython -m pip install -q huggingface_hub requests 2>&1 | Out-Null
        & $prefetchPython $prefetchScript --hf-home $hfHome --tagger-models-dir $taggerModelsDir --if-missing
    }
    $prefetchExit = $LASTEXITCODE
    $ErrorActionPreference = $prevEap

    if ($prefetchExit -ne 0) {
        throw "tagger prefetch failed (exit $prefetchExit). Check HF network or retry with HF_ENDPOINT=https://hf-mirror.com"
    }
    Write-Host "  Cached under tagger-models/ (portable canonical path)" -ForegroundColor Green

    $localTaggerDir = Join-Path $portableDir "tagger-models\wd14\wd14-convnextv2-v2"
    $required = @("model.onnx", "selected_tags.csv")
    foreach ($name in $required) {
        if (-not (Test-Path (Join-Path $localTaggerDir $name))) {
            throw "Default tagger missing in tagger-models after prefetch: $localTaggerDir\$name"
        }
    }

    # Portable offline tagging resolves MIKAZUKI_TAGGER_MODELS_DIR first; drop HF hub duplicate.
    $hubModel = Join-Path $portableDir "huggingface\hub\models--SmilingWolf--wd-v1-4-convnextv2-tagger-v2"
    if (Test-Path $hubModel) {
        Remove-Item $hubModel -Recurse -Force
        Write-Host "  Removed HF hub duplicate (tagger-models is canonical)" -ForegroundColor Green
    }

    $embedSitePackages = Join-Path $pythonDir "Lib\site-packages"
    if (Test-Path $embedSitePackages) {
        Get-ChildItem $embedSitePackages -Force | Remove-Item -Recurse -Force -ErrorAction SilentlyContinue
        Write-Host "  Cleared build-time pip packages from python_embeded" -ForegroundColor Green
    }
}

Write-Host ""
Write-Host "[3b/6] Bundling SD/SDXL/Flux tokenizer cache (~8 MB, offline training)..." -ForegroundColor Cyan

$tokenizerCacheDir = Join-Path $portableDir "tokenizer-cache"
New-Item -ItemType Directory -Path $tokenizerCacheDir -Force | Out-Null
$tokenizerPrefetchScript = Join-Path $sdtDir "scripts\prefetch_sdxl_tokenizer.py"
if (-not (Test-Path $tokenizerPrefetchScript)) {
    throw "prefetch script missing: $tokenizerPrefetchScript"
}

$tokenizerPrefetchPython = $null
if (Test-Path $pythonExe) {
    $tokenizerPrefetchPython = $pythonExe
} elseif (Test-Path (Join-Path $ProjectRoot "venv\Scripts\python.exe")) {
    $tokenizerPrefetchPython = (Join-Path $ProjectRoot "venv\Scripts\python.exe")
} elseif (Get-Command python -ErrorAction SilentlyContinue) {
    $tokenizerPrefetchPython = (Get-Command python).Source
}
if (-not $tokenizerPrefetchPython) {
    throw "No Python available for SDXL tokenizer prefetch"
}

$prevEapTokenizer = $ErrorActionPreference
$ErrorActionPreference = 'Continue'
if ($tokenizerPrefetchPython -eq $pythonExe) {
    if (Test-Path $getPipPath) {
        & $pythonExe $getPipPath --no-warn-script-location 2>&1 | Out-Null
    }
    & $tokenizerPrefetchPython -s -m pip install -q modelscope requests 2>&1 | Out-Null
    & $tokenizerPrefetchPython -s $tokenizerPrefetchScript --cache-dir $tokenizerCacheDir --if-missing --prefer-modelscope
} else {
    & $tokenizerPrefetchPython -m pip install -q modelscope requests 2>&1 | Out-Null
    & $tokenizerPrefetchPython $tokenizerPrefetchScript --cache-dir $tokenizerCacheDir --if-missing --prefer-modelscope
}
$tokenizerPrefetchExit = $LASTEXITCODE
$ErrorActionPreference = $prevEapTokenizer
if ($tokenizerPrefetchExit -ne 0) {
    throw "SDXL tokenizer prefetch failed (exit $tokenizerPrefetchExit)"
}
Write-Host "  Cached under tokenizer-cache/ (offline SD/SDXL/Flux tokenizers)" -ForegroundColor Green

$tokenizerBundles = @(
    @{ Folder = "openai_clip-vit-large-patch14"; Files = @("vocab.json", "merges.txt", "tokenizer.json", "tokenizer_config.json", "special_tokens_map.json") },
    @{ Folder = "laion_CLIP-ViT-bigG-14-laion2B-39B-b160k"; Files = @("vocab.json", "merges.txt", "tokenizer.json", "tokenizer_config.json", "special_tokens_map.json") },
    @{ Folder = "google_t5-v1_1-xxl"; Files = @("spiece.model", "tokenizer_config.json", "special_tokens_map.json") }
)
foreach ($bundle in $tokenizerBundles) {
    foreach ($name in $bundle.Files) {
        $path = Join-Path $tokenizerCacheDir "$($bundle.Folder)\$name"
        if (-not (Test-Path $path)) {
            throw "Tokenizer cache incomplete after prefetch: $path"
        }
    }
}

# ==== Step 4: Create launcher scripts ====

Write-Host ""
Write-Host "[4/6] Creating launcher scripts..." -ForegroundColor Cyan

# run_gui_portable.bat — root shim (logic lives in SD-Trainer/scripts/portable/, updates with project)
$shimSrc = Join-Path $ProjectRoot "scripts\portable\run_gui_portable_shim.bat"
if (Test-Path $shimSrc) {
    Copy-PortableBatchFile $shimSrc (Join-Path $portableDir "run_gui_portable.bat")
    Write-Host "  Created run_gui_portable.bat (shim -> scripts/portable/launch_portable.bat)"
} else {
    Write-Host "  WARNING: scripts/portable/run_gui_portable_shim.bat not found" -ForegroundColor Yellow
}

# Use the repo's run_gui.bat as the portable entrypoint (it auto-detects
# python_embeded and dispatches to run_gui_portable.bat).
$repoRunGui = Join-Path $ProjectRoot "run_gui.bat"
if (Test-Path $repoRunGui) {
    Copy-PortableBatchFile $repoRunGui (Join-Path $portableDir "run_gui.bat")
    Write-Host "  Copied run_gui.bat (unified launcher from repo)"
} else {
    Write-Host "  WARNING: run_gui.bat not found in repo root" -ForegroundColor Yellow
}

# update/
$updateDir = Join-Path $portableDir "update"
New-Item -ItemType Directory -Path $updateDir -Force | Out-Null

$updateBat = "@echo off`r`nchcp 65001 >nul 2>&1`r`n"
$updateBat += "call `"%~dp0..\Update-SD-Trainer.bat`" %*`r`n"
$updateBat += "exit /b %errorlevel%`r`n"
[System.IO.File]::WriteAllText(
    (Join-Path $updateDir "update_sd_trainer.bat"),
    $updateBat,
    (New-Object System.Text.UTF8Encoding $false)
)

$updateReleaseBat = "@echo off`r`nchcp 65001 >nul 2>&1`r`n"
$updateReleaseBat += "call `"%~dp0..\Update-SD-Trainer-Release.bat`" %*`r`n"
$updateReleaseBat += "exit /b %errorlevel%`r`n"
[System.IO.File]::WriteAllText(
    (Join-Path $updateDir "update_from_release.bat"),
    $updateReleaseBat,
    (New-Object System.Text.UTF8Encoding $false)
)

$updateDepsBat = "@echo off`r`nchcp 65001 >nul 2>&1`r`ncd /d `"%~dp0..`"`r`n"
$updateDepsBat += "echo Updating Python dependencies...`r`n"
$updateDepsBat += "`"python_embeded\python.exe`" -s -m pip install --upgrade torch torchvision --index-url https://download.pytorch.org/whl/cu128`r`n"
$updateDepsBat += "`"python_embeded\python.exe`" -s -m pip install --upgrade -r `"SD-Trainer\requirements.txt`"`r`n"
$updateDepsBat += "echo Done.`r`npause`r`n"
[System.IO.File]::WriteAllText(
    (Join-Path $updateDir "update_dependencies.bat"),
    $updateDepsBat,
    (New-Object System.Text.UTF8Encoding $false)
)
Write-Host "  Created update/ scripts"

# install_xformers.bat — one-click xformers installer for portable users
$xformersBat = "@echo off`r`nchcp 65001 >nul 2>&1`r`ntitle Install xformers`r`ncd /d `"%~dp0`"`r`n"
$xformersBat += "set `"PYTHON_EXE=%~dp0python_embeded\python.exe`"`r`n"
$xformersBat += "if not exist `"%PYTHON_EXE%`" (`r`n"
$xformersBat += "    echo [ERROR] python_embeded\python.exe not found!`r`n"
$xformersBat += "    pause`r`n    exit /b 1`r`n)`r`n"
$xformersBat += "echo.`r`necho  Installing xformers 0.0.30 for Torch 2.7.0 + CUDA 12.8 ...`r`necho.`r`n"
$xformersBat += "`"%PYTHON_EXE%`" -s -m pip install xformers==0.0.30 --index-url https://download.pytorch.org/whl/cu128 --no-warn-script-location`r`n"
$xformersBat += "if errorlevel 1 (`r`n    echo [ERROR] xformers installation failed.`r`n    pause`r`n    exit /b 1`r`n)`r`n"
$xformersBat += "echo.`r`necho  Verifying...`r`n"
$xformersBat += "`"%PYTHON_EXE%`" -s -c `"import xformers; print(f'  xformers {xformers.__version__} OK')`"`r`n"
$xformersBat += "echo.`r`necho  Done! You can now use attn_mode = xformers.`r`necho.`r`npause`r`n"
[System.IO.File]::WriteAllText(
    (Join-Path $portableDir "install_xformers.bat"),
    $xformersBat,
    (New-Object System.Text.UTF8Encoding $false)
)
Write-Host "  Created install_xformers.bat"

# Root-level utility bat files
$templateDir = Join-Path $PSScriptRoot "templates"
$portableTemplateDir = Join-Path $sdtDir "scripts\portable\templates"
New-Item -ItemType Directory -Path $portableTemplateDir -Force | Out-Null
foreach ($bat in @("Update-SD-Trainer.bat", "Update-SD-Trainer-Release.bat", "Download-Anima-Model.bat", "Fix-Portable-Bats.bat")) {
    $src = Join-Path $templateDir $bat
    if (-not (Test-Path $src)) {
        $src = Join-Path $ProjectRoot $bat
    }
    if (Test-Path $src) {
        Copy-PortableBatchFile $src (Join-Path $portableDir $bat)
        Copy-PortableBatchFile $src (Join-Path $portableTemplateDir $bat)
        Write-Host "  Created $bat"
    }
}

Write-Host "  Normalizing .bat line endings (CRLF) for Windows cmd..."
Normalize-PortableBatchFilesInTree -Root $portableDir

# ==== Step 5: Empty dirs + README ====

Write-Host ""
Write-Host "[5/6] Creating user directories and README..." -ForegroundColor Cyan

foreach ($d in @("sd-models", "output", "logs", "train")) {
    $p = Join-Path $sdtDir $d
    New-Item -ItemType Directory -Path $p -Force | Out-Null
    [System.IO.File]::WriteAllText((Join-Path $p ".gitkeep"), "")
}

foreach ($d in @("huggingface", "tagger-models", "tagger-models\wd14", "tagger-models\vlm")) {
    $p = Join-Path $portableDir $d
    New-Item -ItemType Directory -Path $p -Force | Out-Null
    [System.IO.File]::WriteAllText((Join-Path $p ".gitkeep"), "")
}

$linkScript = Join-Path $sdtDir "scripts\portable\link_portable_data_dirs.py"
if (Test-Path $linkScript) {
    Write-Host "  Ensuring SD-Trainer data dirs + portable-root junctions..." -ForegroundColor Green
    & $pythonExe -s $linkScript --trainer-dir $sdtDir
    if ($LASTEXITCODE -ne 0) {
        Write-Host "  WARNING: portable data-dir junction step failed (exit $LASTEXITCODE)" -ForegroundColor Yellow
    }
}

$readme = "SD-Trainer Portable`r`n"
$readme += "===================`r`n`r`n"
$readme += "Quick Start:`r`n"
$readme += "  1. Double-click run_gui.bat`r`n"
$readme += "  2. First launch requires internet (downloads ~3 GB of PyTorch)`r`n"
$readme += "  3. Open http://127.0.0.1:28000 in browser`r`n`r`n"
$readme += "Tagging:`r`n"
$readme += "  Default WD tagger (wd14-convnextv2-v2) is bundled under tagger-models/wd14/`r`n"
$readme += "  (~400 MB). Put extra WD/CL tag models in tagger-models/wd14/<model-key>/`r`n"
$readme += "  Future VLM caption models can be placed under tagger-models/vlm/<model-key>/`r`n"
$readme += "  with the files required by that model, such as model.onnx and selected_tags.csv.`r`n`r`n"
$readme += "Directories:`r`n"
$readme += "  run_gui.bat      - Stable entrypoint for portable users`r`n"
$readme += "  run_gui_portable.bat - Legacy shim (logic in SD-Trainer/scripts/portable/)`r`n"
$readme += "  python_embeded/  - Python runtime`r`n"
$readme += "  SD-Trainer/      - Project files`r`n"
$readme += "  SD-Trainer\\sd-models\\  - Models (file picker; put models here)`r`n"
$readme += "  SD-Trainer\\output\\    - Training output`r`n"
$readme += "  SD-Trainer\\logs\\       - Logs`r`n"
$readme += "  sd-models\\ / output\\ / logs\\ at package root - junctions to SD-Trainer (legacy paths)`r`n"
$readme += "  tagger-models/   - Local tagger models`r`n`r`n"
$readme += "Update:`r`n"
$readme += "  Update-SD-Trainer.bat                - Git update (recommended if .git exists)`r`n"
$readme += "  Update-SD-Trainer-Release.bat      - Download latest Release 7z and merge`r`n"
$readme += "  update\update_sd_trainer.bat       - Shortcut to Update-SD-Trainer.bat`r`n"
$readme += "  update\update_from_release.bat     - Shortcut to Update-SD-Trainer-Release.bat`r`n"
$readme += "  update\update_dependencies.bat     - Update Python packages`r`n`r`n"
$readme += "Requirements:`r`n"
$readme += "  - Windows 10/11 64-bit`r`n"
$readme += "  - NVIDIA GPU (RTX 20-series or newer)`r`n"
$readme += "  - ~7 GB disk + ~3 GB download on first run`r`n`r`n"
$readme += "xformers (recommended):`r`n"
$readme += "  If xformers is missing, double-click install_xformers.bat to install.`r`n"
$readme += "  xformers provides faster attention than PyTorch SDPA on most GPUs.`r`n`r`n"
$readme += "Flash Attention 2:`r`n"
$readme += "  This portable package does NOT use flash-attn (uses xformers / PyTorch SDPA).`r`n"
$readme += "  Do not pip install flash-attn into python_embeded. See README in SD-Trainer/.`r`n"
[System.IO.File]::WriteAllText(
    (Join-Path $portableDir "README.txt"),
    $readme,
    (New-Object System.Text.UTF8Encoding $true)
)
Write-Host "  Created README.txt"
Write-Host "  Done" -ForegroundColor Green

# ==== Step 5: 7z archive ====

if (-not $Skip7z) {
    Write-Host ""
    Write-Host "[6/6] Creating 7z archive..." -ForegroundColor Cyan

    if (-not $7zExe) {
        Write-Host "  [!] 7-Zip not found, skipping compression." -ForegroundColor Yellow
    } else {
        $archiveName = "SD-Trainer-v${Version}.7z"
        $archivePath = Join-Path $buildDir $archiveName
        if (Test-Path $archivePath) { Remove-Item $archivePath -Force }

        # 7-Zip follows Windows directory junctions and its recursive exclude
        # patterns also match same-named canonical dirs under SD-Trainer.
        # Temporarily remove only the portable-root compatibility junctions.
        $archiveJunctionNames = @("sd-models", "output", "logs", "train")
        foreach ($name in $archiveJunctionNames) {
            $canonicalPath = Join-Path $sdtDir $name
            $unexpected = @(
                Get-ChildItem -LiteralPath $canonicalPath -Force -ErrorAction SilentlyContinue |
                    Where-Object { $_.Name -ne ".gitkeep" }
            )
            if ($unexpected.Count -gt 0) {
                throw "refusing to archive non-empty generated data directory: $canonicalPath (use -Clean)"
            }
        }
        $removedArchiveJunctions = @()
        $archiveExitCode = 1
        $restoreExitCode = 0
        try {
            foreach ($name in $archiveJunctionNames) {
                $junctionPath = Join-Path $portableDir $name
                $item = Get-Item -LiteralPath $junctionPath -Force -ErrorAction SilentlyContinue
                if (-not $item) {
                    throw "portable-root data junction missing before archive: $junctionPath"
                }
                if (-not ($item.Attributes -band [System.IO.FileAttributes]::ReparsePoint)) {
                    throw "expected portable-root data junction before archive: $junctionPath"
                }
                $removeCommand = 'rmdir "' + $junctionPath + '"'
                & cmd.exe /d /c $removeCommand | Out-Null
                if ($LASTEXITCODE -ne 0) {
                    throw "failed to remove archive-time junction: $junctionPath"
                }
                $removedArchiveJunctions += $name
            }

            Write-Host "  Compressing..."
            & $7zExe a -t7z -mx=9 -m0=LZMA2:d=64m -mmt=on $archivePath "$portableDir\*" | Out-Null
            $archiveExitCode = $LASTEXITCODE
        } finally {
            if ($removedArchiveJunctions.Count -gt 0 -and (Test-Path $linkScript)) {
                & $pythonExe -s $linkScript --trainer-dir $sdtDir | Out-Null
                $restoreExitCode = $LASTEXITCODE
                if ($restoreExitCode -eq 0) {
                    foreach ($name in $removedArchiveJunctions) {
                        $restoredPath = Join-Path $portableDir $name
                        $restoredItem = Get-Item -LiteralPath $restoredPath -Force -ErrorAction SilentlyContinue
                        if (-not $restoredItem -or -not ($restoredItem.Attributes -band [System.IO.FileAttributes]::ReparsePoint)) {
                            $restoreExitCode = 1
                            break
                        }
                    }
                }
            } elseif ($removedArchiveJunctions.Count -gt 0) {
                $restoreExitCode = 1
            }
        }
        if ($archiveExitCode -ne 0) {
            throw "7-Zip archive creation failed (exit $archiveExitCode)"
        }
        if ($restoreExitCode -ne 0) {
            throw "failed to restore portable-root data junctions after archive"
        }

        $sizeBytes = (Get-Item $archivePath).Length
        $sizeMB = [math]::Round($sizeBytes / 1MB, 1)
        Write-Host "  Output: $archiveName  ($sizeMB MB)" -ForegroundColor Green
    }
} else {
    Write-Host ""
    Write-Host "[6/6] Skipping 7z compression" -ForegroundColor Yellow
}

# ==== Done ====

$duration = (Get-Date) - $startTime
Write-Host ""
Write-Host "  Build complete!  ($portableDir)" -ForegroundColor Green
Write-Host "  Elapsed: $($duration.ToString('mm\:ss'))"
Write-Host ""
