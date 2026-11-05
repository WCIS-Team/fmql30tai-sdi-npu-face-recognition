param([switch]$Demo, [int]$Port = 8088, [switch]$NoOpenBrowser)
$ErrorActionPreference = 'Stop'
if ($Port -lt 1 -or $Port -gt 65535) { throw 'Invalid port' }
$taskPython = (Get-Command python.exe -ErrorAction Stop).Source
$taskRoot = $PSScriptRoot
$taskDemoProcess = $null
if (Get-NetTCPConnection -State Listen -LocalPort $Port -ErrorAction SilentlyContinue) {
    throw "Port $Port is already in use. Use the running receiver or choose another port."
}
Write-Host "Browser viewer: http://127.0.0.1:$Port/"
$taskPhysical = @(Get-NetAdapter | Where-Object { $_.HardwareInterface -and $_.Status -eq 'Up' } | Select-Object -ExpandProperty ifIndex)
Get-NetIPAddress -AddressFamily IPv4 | Where-Object { $_.InterfaceIndex -in $taskPhysical -and $_.IPAddress -notlike '169.254.*' } | ForEach-Object {
    Write-Host ('LAN viewer: http://' + $_.IPAddress + ':' + $Port + '/')
}
if ($Demo) {
    Write-Host 'DEMO: generated test frames only; no camera hardware is opened.'
    # The publisher waits for the receiver and stops with this launcher.
    $taskDemoRunner = Join-Path $taskRoot 'demo-preview.py'
    $taskDemoArgs = '"' + $taskDemoRunner + '" --port ' + $Port
    $taskDemoProcess = Start-Process -FilePath $taskPython -ArgumentList $taskDemoArgs -WindowStyle Hidden -PassThru
}
if (-not $NoOpenBrowser) { Start-Process ('http://127.0.0.1:' + $Port + '/') }
try {
    & $taskPython -u (Join-Path $taskRoot 'server.py') --host 0.0.0.0 --port $Port
} finally {
    if ($taskDemoProcess -and -not $taskDemoProcess.HasExited) {
        Stop-Process -Id $taskDemoProcess.Id -ErrorAction SilentlyContinue
    }
}
