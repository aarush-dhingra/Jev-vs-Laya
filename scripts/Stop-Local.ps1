param([ValidateSet('all','server','laya')][string]$Service = 'all')
$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
$arenaPython = Join-Path $projectRoot '.venv\Scripts\python.exe'
$modules = @('arena.server', 'arena.laya_worker')
if ($Service -eq 'server') { $modules = @('arena.server') }
if ($Service -eq 'laya') { $modules = @('arena.laya_worker') }
$pythonProcesses = @(Get-CimInstance Win32_Process -Filter "Name='python.exe'")
$projectParents = @($pythonProcesses | Where-Object { $_.ExecutablePath -eq $arenaPython } | Select-Object -ExpandProperty ProcessId)
# Windows virtual environments launch a base-Python child. Include only children
# of this project's interpreter, and still require an exact service module match.
foreach ($process in $pythonProcesses) {
    $belongsToProject = $process.ExecutablePath -eq $arenaPython -or $process.ParentProcessId -in $projectParents
    if (-not $belongsToProject -or -not $process.CommandLine) { continue }
    foreach ($module in $modules) {
        if ($process.CommandLine -match ('(?:^|\s)-m\s+' + [regex]::Escape($module) + '(?:\s|$)')) {
            Stop-Process -Id $process.ProcessId -ErrorAction SilentlyContinue
            Write-Host "Stopped $module ($($process.ProcessId))."
        }
    }
}
