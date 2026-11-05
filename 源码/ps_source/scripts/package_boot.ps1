$ErrorActionPreference = 'Stop'
$taskRoot = Split-Path -Parent $PSScriptRoot
$taskProcise = 'C:\FudanMicro\Procise'
$env:TCL_LIBRARY = Join-Path $taskProcise 'tcl8.4'
$env:PATH = "$taskProcise\dll;$taskProcise\bin;" + $env:PATH
$env:ICTIME_HOME = $taskProcise
$env:APP_DIR = $taskProcise
$env:FMSH_DB = Join-Path $taskProcise 'db'
$taskStarted = Get-Date
# Procise is a Windows GUI-subsystem executable even in script mode. Explicitly
# wait for its process; a bare native invocation can return before its work.
$taskProcess = Start-Process -FilePath (Join-Path $taskProcise 'bin/procise.exe') `
    -ArgumentList (Join-Path $taskRoot 'scripts/package_boot.tcl') `
    -WorkingDirectory $taskRoot -WindowStyle Hidden -Wait -PassThru `
    -RedirectStandardOutput (Join-Path $taskRoot 'outputs/boot_pack.log') `
    -RedirectStandardError (Join-Path $taskRoot 'outputs/boot_pack_errors.log')
Get-Content -LiteralPath (Join-Path $taskRoot 'outputs/boot_pack.log') | Write-Output
Write-Output ('PROCISE_EXIT=' + $taskProcess.ExitCode)
if($taskProcess.ExitCode -ne 0) { throw "Procise packaging process failed" }
$taskMarker = Get-Item -LiteralPath (Join-Path $taskRoot 'outputs/release-candidate/procise-package-status.txt')
if($taskMarker.LastWriteTime -lt $taskStarted) { throw 'Procise completion marker is stale' }
