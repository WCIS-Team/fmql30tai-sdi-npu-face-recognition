# Run from the private school task root. Shared SDK/toolchain are read-only.
param([Parameter(Mandatory=$true)][string]$TaskRoot)
$ErrorActionPreference='Stop'
$ProgressPreference='SilentlyContinue'
$taskPath=[System.IO.Path]::GetFullPath($TaskRoot).Replace('\','/')
if(-not $taskPath.ToLowerInvariant().StartsWith('d:/yzd/tmp/wcis-face-parallel-')){throw 'Use an isolated parallel task directory'}
$env:TMP="$taskPath/scratch"; $env:TEMP=$env:TMP; $env:TMPDIR=$env:TMP
$env:XDG_CACHE_HOME="$taskPath/cache"
$env:MSYS2_ARG_CONV_EXCL='*'
$env:CROSSWIN_TC='D:/yzd/tools/cross/gcc-arm-10.3-2021.07-mingw-w64-i686-aarch64-none-linux-gnu'
$env:PATH="$env:CROSSWIN_TC/bin;D:/yzd/MSYS2/mingw64/bin;D:/yzd/MSYS2/usr/bin;"+$env:PATH
Get-Process python,cmake,ninja -ErrorAction SilentlyContinue | Select-Object Id,ProcessName
foreach($name in @('scratch','cache')){New-Item -ItemType Directory -Path "$taskPath/$name" -Force | Out-Null}
Set-Location -LiteralPath $taskPath
$sourcePath="$taskPath/cross-source/npu_photo"
& cmake.exe -G Ninja -S $sourcePath -B "$taskPath/npu-build" '-DCMAKE_TOOLCHAIN_FILE=D:/yzd/WCIS/crosswin/cmake/crosswin-toolchain.cmake' "-DCROSSWIN_TC=$env:CROSSWIN_TC" '-DCMAKE_PREFIX_PATH=D:/yzd/WCIS/crosswin/kit/cmake' '-DWCIS_UAPI_ROOT=D:/yzd/WCIS/crosswin/uapi' '-DCMAKE_POLICY_VERSION_MINIMUM=3.5' '-DCMAKE_BUILD_TYPE=Release'
if($LASTEXITCODE -ne 0){exit $LASTEXITCODE}
& cmake.exe --build "$taskPath/npu-build" --target wcis_npu_jpeg_parallel --parallel 2
exit $LASTEXITCODE
