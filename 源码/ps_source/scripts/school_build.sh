#!/usr/bin/env bash
set -euo pipefail
task_here="$(cd -- "$(dirname -- "$0")" && pwd -P)"
case "$task_here" in /d/yzd/tmp/*) ;; *) echo 'Unsafe task root'; exit 2;; esac
mkdir -p "$task_here/scratch" "$task_here/cache" "$task_here/logs"
export TMP="$(cygpath -m "$task_here/scratch")"
export TEMP="$TMP" TMPDIR="$TMP" XDG_CACHE_HOME="$task_here/cache"
task_tc='/d/yzd/tools/cross/gcc-arm-10.3-2021.07-mingw-w64-i686-aarch64-none-linux-gnu'
task_kit='/d/yzd/WCIS/crosswin/kit'
export PATH="$task_tc/bin:/d/yzd/MSYS2/mingw64/bin:$PATH"
export CROSSWIN_TC="$(cygpath -m "$task_tc")"
cd "$task_here"
exec > >(tee "$task_here/logs/build.log") 2>&1
task_python_count=$(MSYS2_ARG_CONV_EXCL='*' /c/Windows/System32/WindowsPowerShell/v1.0/powershell.exe -NoProfile -Command '@(Get-Process -Name python,pythonw -ErrorAction SilentlyContinue).Count' | tr -d '\r\n ')
echo "PYTHON_PROCESS_COUNT=$task_python_count"
if [[ "$task_python_count" != 0 ]]; then
    echo 'Existing Python jobs found; defer compilation without interrupting them.'; exit 9
fi
tar -xzf ps_app_source.tar.gz -C "$task_here"
cmake.exe -G Ninja -S "$(cygpath -m "$task_here/ps_app")" -B "$(cygpath -m "$task_here/build")" \
  -DCMAKE_TOOLCHAIN_FILE="$(cygpath -m /d/yzd/WCIS/crosswin/cmake/crosswin-toolchain.cmake)" \
  -DCROSSWIN_TC="$CROSSWIN_TC" \
  -DCMAKE_PREFIX_PATH="$(cygpath -m "$task_kit/cmake")" \
  -DMODELZOO_STATIC="$(cygpath -m "$task_kit/ModelzooDeps/aarch64/Static")" \
  -DMODELZOO_DYNAMIC="$(cygpath -m "$task_kit/ModelzooDeps/aarch64/Dynamic")" \
  -DWCIS_UAPI_ROOT=D:/yzd/WCIS/crosswin/uapi \
  -DCMAKE_EXPORT_COMPILE_COMMANDS=ON -DCMAKE_BUILD_TYPE=Release \
  -DCMAKE_POLICY_VERSION_MINIMUM=3.5
cmake.exe --build "$(cygpath -m "$task_here/build")" -j2
task_bin="$task_here/build/wcis_sdi_reference"
[[ -f "$task_bin" ]] || task_bin="$task_bin.exe"
"$task_tc/bin/aarch64-none-linux-gnu-readelf.exe" -h "$task_bin" > "$task_here/logs/elf-header.txt"
"$task_tc/bin/aarch64-none-linux-gnu-readelf.exe" -d "$task_bin" > "$task_here/logs/elf-dynamic.txt"
"$task_tc/bin/aarch64-none-linux-gnu-readelf.exe" -V "$task_bin" > "$task_here/logs/elf-versions.txt"
grep -q 'Class: *ELF64' "$task_here/logs/elf-header.txt"
grep -q 'Machine: *AArch64' "$task_here/logs/elf-header.txt"
sha256sum "$task_bin" | tee "$task_here/logs/binary.sha256"
echo "WCIS SERVER BUILD COMPLETE: $task_bin"
