param([string]$Iverilog = 'C:\msys64\ucrt64\bin\iverilog.exe', [string]$Vvp = 'C:\msys64\ucrt64\bin\vvp.exe')
$ErrorActionPreference = 'Stop'
$taskRoot = Split-Path -Parent $PSScriptRoot
$taskOut = Join-Path $taskRoot 'outputs/sim'
New-Item -ItemType Directory -Force -Path $taskOut | Out-Null
$taskSuites = @(
    @{Name='sdi_monitor'; Sources=@('rtl/wcis_sdi_monitor.v','sim/tb_sdi_monitor.sv')},
    @{Name='vtc_pipeline'; Sources=@('case/rtl/display/vtc.v','sim/vtc_vendor_reference.v','sim/tb_vtc_pipeline.sv')},
    @{Name='vtc_resize_chain'; Sources=@('case/rtl/display/vtc.v','rtl/wcis_frame_rate_gate.v','case/rtl/display/cmos_resize_24bit.v','sim/tb_vtc_resize_chain.sv')},
    @{Name='frame_rate_gate'; Sources=@('rtl/wcis_frame_rate_gate.v','sim/tb_frame_rate_gate.sv')},
    @{Name='stream_letterbox'; Sources=@('rtl/wcis_stream_letterbox.v','sim/tb_stream_letterbox.sv')},
    @{Name='case_registers'; Sources=@('case/rtl/display/bridge_s.v','case/rtl/display/level_cross.v','case/rtl/display/pulse_cross_camera.v','case/rtl/display/frame_ctrl.v','rtl/wcis_frame_rate_gate.v','sim/tb_case_registers.sv')},
    @{Name='case_resize'; Sources=@('case/rtl/display/cmos_resize_24bit.v','sim/tb_case_resize.sv')}
)
$taskResults = @()
foreach($taskSuite in $taskSuites) {
    $taskExe = Join-Path $taskOut ($taskSuite.Name + '.vvp')
    $taskSources = @($taskSuite.Sources | ForEach-Object { Join-Path $taskRoot $_ })
    # Windows PowerShell represents native stderr warnings as ErrorRecords.
    # Judge the compiler's exit code, not the presence of a harmless warning.
    $ErrorActionPreference = 'Continue'
    $taskCompile = & $Iverilog -g2012 -Wall -s ('tb_' + $taskSuite.Name) -o $taskExe @taskSources 2>&1
    $taskCompileCode = $LASTEXITCODE
    $ErrorActionPreference = 'Stop'
    # Write even when compilation emits nothing, clearing any old warning log.
    Set-Content -Encoding utf8 -Path (Join-Path $taskOut ($taskSuite.Name + '-compile.log')) -Value ($taskCompile -join "`n")
    if($taskCompileCode -ne 0) { throw ('Compilation failed: ' + $taskSuite.Name + ' ' + ($taskCompile -join "`n")) }
    $taskRun = & $Vvp $taskExe 2>&1
    $taskCode = $LASTEXITCODE
    $taskRun | Set-Content -Encoding utf8 (Join-Path $taskOut ($taskSuite.Name + '.log'))
    $taskRun | Write-Output
    if($taskCode -ne 0 -or -not ($taskRun -match '^PASS ')) { throw ('Simulation failed: ' + $taskSuite.Name) }
    $taskResults += @{suite=$taskSuite.Name;passed=$true}
}
@{suites=$taskResults;board_verified=$false;bitstream_generated=$false} | ConvertTo-Json -Depth 5 | Set-Content -Encoding utf8 (Join-Path $taskOut 'summary.json')
