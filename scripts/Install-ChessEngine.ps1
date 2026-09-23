$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
Set-Location -LiteralPath $projectRoot
$release = Invoke-RestMethod https://api.github.com/repos/official-stockfish/Stockfish/releases/tags/sf_19
$asset = $release.assets | Where-Object name -eq 'stockfish-windows-x86-64-universal.zip'
New-Item -ItemType Directory -Force var/tools/stockfish | Out-Null
Invoke-WebRequest $asset.browser_download_url -OutFile var/tools/stockfish.zip
Expand-Archive -LiteralPath var/tools/stockfish.zip -DestinationPath var/tools/stockfish -Force
Write-Host 'Stockfish 19 installed. License and source are included in var/tools/stockfish.'
