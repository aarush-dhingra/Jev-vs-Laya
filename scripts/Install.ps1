param([switch]$Models)
$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
Set-Location -LiteralPath $projectRoot
if (-not (Test-Path -LiteralPath '.venv\Scripts\python.exe')) {
    python -m venv .venv
    if ($LASTEXITCODE -ne 0) { throw 'Python 3.12 is required. Install Python and retry.' }
}
$arenaPython = Join-Path $projectRoot '.venv\Scripts\python.exe'
& $arenaPython -m pip install -e "."
if ($LASTEXITCODE -ne 0) { throw 'Chess dependency installation failed.' }
if ($Models) {
    & $arenaPython -m pip install -e ".[models]"
    if ($LASTEXITCODE -ne 0) { throw 'Model dependency installation failed.' }
}
if (-not (Test-Path -LiteralPath '.env')) { Copy-Item -LiteralPath '.env.example' -Destination '.env' }
Write-Host 'Ready. Run .\scripts\Start-Local.ps1 and open http://127.0.0.1:8765'
if (-not $Models) { Write-Host 'For local Laya dependencies: .\scripts\Install.ps1 -Models' }
