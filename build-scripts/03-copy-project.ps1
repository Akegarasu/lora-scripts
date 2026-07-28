# 03-copy-project.ps1
# 复制项目文件到便携式环境（排除模型目录）

param(
    [string]$BuildDir = (Join-Path (Split-Path $PSScriptRoot -Parent) "build\sd-trainer-portable"),
    [string]$ProjectRoot = (Split-Path $PSScriptRoot -Parent)
)

$ErrorActionPreference = "Stop"

Write-Host "=== 复制项目文件 ===" -ForegroundColor Cyan

& (Join-Path $ProjectRoot "build-scripts\00-build-frontend.ps1") -ProjectRoot $ProjectRoot
if ($LASTEXITCODE -ne 0) { throw "前端构建失败" }

# 确保子模块已初始化
Write-Host "初始化 git 子模块..."
Push-Location $ProjectRoot
git submodule update --init --recursive 2>&1 | Out-Null
Pop-Location

# 目标目录
$targetDir = Join-Path $BuildDir "lora-scripts-next"

# 排除的目录（包括模型目录）
$excludeDirs = @(
    ".git",
    "venv",
    ".venv",
    "__pycache__",
    "build",
    "build-scripts",
    "node_modules",
    "logs",
    "output",
    "huggingface",
    "tagger-models",
    "sd-models",
    "wd14_tagger_model",
    "train",
    "extensions",
    ".idea",
    ".vscode",
    ".sisyphus",
    ".playwright-mcp"
)

# 使用 robocopy 复制
Write-Host "复制项目文件（排除模型目录）..."
$excludeArgs = $excludeDirs | ForEach-Object { "/XD", $_ }
robocopy $ProjectRoot $targetDir /E /NFL /NDL /NJH /NJS /NC @excludeArgs | Out-Null

# robocopy 返回码: 0-7 表示成功
if ($LASTEXITCODE -gt 7) {
    throw "复制文件失败 (robocopy exit code: $LASTEXITCODE)"
}

Write-Host "项目文件复制完成" -ForegroundColor Green

# 创建用户目录
Write-Host "创建用户目录..."
New-Item -ItemType Directory -Path (Join-Path $BuildDir "sd-models") -Force | Out-Null
New-Item -ItemType Directory -Path (Join-Path $BuildDir "output") -Force | Out-Null
New-Item -ItemType Directory -Path (Join-Path $BuildDir "logs") -Force | Out-Null
New-Item -ItemType Directory -Path (Join-Path $BuildDir "huggingface") -Force | Out-Null
New-Item -ItemType Directory -Path (Join-Path $BuildDir "tagger-models") -Force | Out-Null
New-Item -ItemType Directory -Path (Join-Path $BuildDir "tagger-models\wd14") -Force | Out-Null
New-Item -ItemType Directory -Path (Join-Path $BuildDir "tagger-models\vlm") -Force | Out-Null

Write-Host "用户目录创建完成" -ForegroundColor Green

exit 0
