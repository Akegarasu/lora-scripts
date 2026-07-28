param(
    [string]$ProjectRoot = (Split-Path $PSScriptRoot -Parent)
)

$ErrorActionPreference = "Stop"
$frontendDir = Join-Path $ProjectRoot "frontend"
$packageLock = Join-Path $frontendDir "package-lock.json"

if (-not (Test-Path $packageLock)) {
    throw "Frontend lockfile not found: $packageLock"
}

$nodeVersion = (& node --version 2>$null)
if ($LASTEXITCODE -ne 0 -or -not $nodeVersion) {
    throw "Node.js 22 is required to build frontend/dist"
}
if ($nodeVersion -notmatch '^v22\.') {
    throw "Node.js 22 is required; found $nodeVersion"
}

Write-Host "Building Vue frontend with $nodeVersion..." -ForegroundColor Cyan
& npm --prefix $frontendDir ci
if ($LASTEXITCODE -ne 0) { throw "Frontend dependency installation failed" }
& npm --prefix $frontendDir run check
if ($LASTEXITCODE -ne 0) { throw "Frontend checks or build failed" }

$index = Join-Path $frontendDir "dist\index.html"
if (-not (Test-Path $index)) {
    throw "Frontend build did not produce $index"
}
Write-Host "Frontend build complete." -ForegroundColor Green
