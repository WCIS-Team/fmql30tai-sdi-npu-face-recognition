#!/usr/bin/env bash
set -euo pipefail
task_here="$(cd -- "$(dirname -- "$0")" && pwd -P)"
case "$task_here" in /d/yzd/tmp/wcis-camera-preview-*) ;; *) exit 2;; esac
mkdir -p "$task_here/scratch" "$task_here/cache"
export TMP="$(cygpath -m "$task_here/scratch")" TEMP="$(cygpath -m "$task_here/scratch")" TMPDIR="$(cygpath -m "$task_here/scratch")"
export XDG_CACHE_HOME="$task_here/cache"
task_tc='/d/yzd/tools/cross/gcc-arm-10.3-2021.07-mingw-w64-i686-aarch64-none-linux-gnu'
task_kit='/d/yzd/WCIS/crosswin/kit'
export PATH="$task_tc/bin:/d/yzd/MSYS2/mingw64/bin:$PATH"
export CROSSWIN_TC="$(cygpath -m "$task_tc")"
task_jobs=$(MSYS2_ARG_CONV_EXCL='*' /c/Windows/System32/WindowsPowerShell/v1.0/powershell.exe -NoProfile -Command '@(Get-Process -Name python,pythonw -ErrorAction SilentlyContinue).Count' | tr -d '\r\n ')
echo "Existing Python jobs: $task_jobs"
# Inventory is informational: a Python process is not evidence of resource exhaustion.
# This isolated single-target build uses at most two compiler jobs and never stops others.
cd "$task_here"
tar -xzf source.tar.gz
cmake.exe -G Ninja -S "$(cygpath -m "$task_here/ps_app")" -B "$(cygpath -m "$task_here/build")" \
  -DCMAKE_TOOLCHAIN_FILE=D:/yzd/WCIS/crosswin/cmake/crosswin-toolchain.cmake \
  -DCROSSWIN_TC="$(cygpath -m "$task_tc")" -DCMAKE_PREFIX_PATH="$(cygpath -m "$task_kit/cmake")" \
  -DMODELZOO_STATIC="$(cygpath -m "$task_kit/ModelzooDeps/aarch64/Static")" \
  -DMODELZOO_DYNAMIC="$(cygpath -m "$task_kit/ModelzooDeps/aarch64/Dynamic")" \
  -DWCIS_UAPI_ROOT=D:/yzd/WCIS/crosswin/uapi -DWCIS_BUILD_REFERENCE=OFF \
  -DCMAKE_POLICY_VERSION_MINIMUM=3.5 -DCMAKE_BUILD_TYPE=Release
cmake.exe --build "$(cygpath -m "$task_here/build")" --target wcis_camera_preview wcis_capture_wait_test -j2
for task_type in h d V; do
  case "$task_type" in h) task_name=header;; d) task_name=dynamic;; V) task_name=versions;; esac
  "$task_tc/bin/aarch64-none-linux-gnu-readelf.exe" "-$task_type" "$task_here/build/wcis_camera_preview" > "$task_here/build/elf-$task_name.txt"
done
