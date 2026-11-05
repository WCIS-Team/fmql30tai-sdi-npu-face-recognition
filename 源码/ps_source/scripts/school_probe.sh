#!/usr/bin/env bash
# Read-only tool/job inventory. Upload this script only to D:/yzd/tmp/<task>.
set -u
task_here="$(cd -- "$(dirname -- "$0")" && pwd -P)"
case "$task_here" in
  /d/yzd/tmp/*) ;;
  *) echo 'Refusing to run outside /d/yzd/tmp/<task>'; exit 2 ;;
esac
mkdir -p "$task_here/scratch" "$task_here/cache"
export TMP="$(cygpath -m "$task_here/scratch")"
export TEMP="$TMP" TMPDIR="$TMP"
export XDG_CACHE_HOME="$task_here/cache"
cd "$task_here"
printf 'TASK_ROOT=%s\n' "$task_here"
printf 'TMP=%s\n' "$TMP"
printf 'HOST=%s\n' "$(uname -s)"
printf 'PROCESSOR_COUNT=%s\n' "${NUMBER_OF_PROCESSORS:-unknown}"
printf 'EXISTING_PYTHON_JOBS:\n'
MSYS2_ARG_CONV_EXCL='*' /c/Windows/System32/tasklist.exe /FI 'IMAGENAME eq python.exe' /FO CSV /NH
printf 'BUILD_TOOLS:\n'
command -v cmake ninja
cmake --version | head -1
ninja --version
printf 'COMPILER:\n'
task_gcc='/d/yzd/tools/cross/gcc-arm-10.3-2021.07-mingw-w64-i686-aarch64-none-linux-gnu/bin/aarch64-none-linux-gnu-g++.exe'
if [[ -f "$task_gcc" ]]; then "$task_gcc" --version | head -1; else echo 'Expected compiler missing'; fi
printf 'SHARED_KIT_READ_ONLY:\n'
ls -ld /d/yzd/WCIS/crosswin/kit /d/yzd/WCIS/crosswin/uapi /d/yzd/WCIS/crosswin/cmake
printf 'EXISTING_BUILD_RECIPE_READ_ONLY:\n'
sed -n '1,200p' /d/yzd/WCIS/crosswin/build.sh
printf 'EXISTING_TOOLCHAIN_RECIPES_READ_ONLY:\n'
find /d/yzd/WCIS/crosswin/cmake -maxdepth 1 -type f -name '*.cmake' -print
printf 'KIT_LAYOUT_READ_ONLY:\n'
find /d/yzd/WCIS/crosswin/kit -maxdepth 3 -type d | head -40
printf 'DISK:\n'
df -h /d/yzd/tmp
