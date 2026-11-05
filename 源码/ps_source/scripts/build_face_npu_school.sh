#!/usr/bin/env bash
set -euo pipefail
task_here="$(cd -- "$(dirname -- "$0")" && pwd -P)"
case "$task_here" in /d/yzd/tmp/wcis-face-*) ;; *) exit 2;; esac
mkdir -p "$task_here/scratch" "$task_here/cache"
export TMP="$(cygpath -m "$task_here/scratch")" TEMP="$(cygpath -m "$task_here/scratch")" TMPDIR="$(cygpath -m "$task_here/scratch")"
export XDG_CACHE_HOME="$task_here/cache"
export PATH="/d/yzd/tools/cross/gcc-arm-10.3-2021.07-mingw-w64-i686-aarch64-none-linux-gnu/bin:/d/yzd/MSYS2/mingw64/bin:$PATH"
task_tc='D:/yzd/tools/cross/gcc-arm-10.3-2021.07-mingw-w64-i686-aarch64-none-linux-gnu'
export CROSSWIN_TC="$task_tc"
cd "$task_here"
tar -xzf npu-source.tar.gz
cmake.exe -G Ninja -S "$(cygpath -m "$task_here/npu_photo")" -B "$(cygpath -m "$task_here/npu-build")" \
 -DCMAKE_TOOLCHAIN_FILE=D:/yzd/WCIS/crosswin/cmake/crosswin-toolchain.cmake \
 -DCROSSWIN_TC="$task_tc" -DCMAKE_PREFIX_PATH=D:/yzd/WCIS/crosswin/kit/cmake \
 -DWCIS_UAPI_ROOT=D:/yzd/WCIS/crosswin/uapi -DCMAKE_POLICY_VERSION_MINIMUM=3.5 -DCMAKE_BUILD_TYPE=Release
cmake.exe --build "$(cygpath -m "$task_here/npu-build")" -j2
"$task_tc/bin/aarch64-none-linux-gnu-readelf.exe" -h "$task_here/npu-build/wcis_face_npu" > "$task_here/npu-build/elf-header.txt"
"$task_tc/bin/aarch64-none-linux-gnu-readelf.exe" -d "$task_here/npu-build/wcis_face_npu" > "$task_here/npu-build/elf-dynamic.txt"
