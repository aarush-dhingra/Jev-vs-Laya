param([ValidateSet('auto','cpu','cuda')][string]$Device = 'auto')
$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
Set-Location -LiteralPath $projectRoot
$arenaPython = Join-Path $projectRoot '.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $arenaPython)) { throw 'Run .\scripts\Install.ps1 -Models first.' }
New-Item -ItemType Directory -Force (Join-Path $projectRoot 'var/logs') | Out-Null
$arenaServices = @(
    @{ Port = 8765; Health = '/api/health'; Script = 'arena.server'; Args = ''; Log = 'server' },
    @{ Port = 8766; Health = '/health'; Script = 'arena.laya_worker'; Args = " --device $Device"; Log = 'laya-worker' }
)
foreach ($arenaService in $arenaServices) {
    $arenaAvailable = $false
    try {
        $null = Invoke-RestMethod "http://127.0.0.1:$($arenaService.Port)$($arenaService.Health)" -TimeoutSec 2
        $arenaAvailable = $true
    } catch { }
    if ($arenaAvailable) { Write-Host "$($arenaService.Script) is already running."; continue }
    $arenaArgs = '-m ' + $arenaService.Script + $arenaService.Args
    Start-Process -FilePath $arenaPython -ArgumentList $arenaArgs -WorkingDirectory $projectRoot -WindowStyle Hidden -RedirectStandardOutput (Join-Path $projectRoot "var/logs/$($arenaService.Log).log") -RedirectStandardError (Join-Path $projectRoot "var/logs/$($arenaService.Log)-error.log")
}
Write-Host 'Dashboard: http://127.0.0.1:8765'
Write-Host 'Laya may take a moment to load. Click Refresh below the match controls.'
Write-Host 'Stop both background services with .\scripts\Stop-Local.ps1'
