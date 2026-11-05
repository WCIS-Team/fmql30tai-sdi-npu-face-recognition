#!/usr/bin/env bash
set -euo pipefail
task_here="$(cd -- "$(dirname -- "$0")" && pwd -P)"
case "$task_here" in /d/yzd/tmp/wcis-lan-*) ;; *) exit 2 ;; esac
task_tc='/d/yzd/tools/cross/gcc-arm-10.3-2021.07-mingw-w64-i686-aarch64-none-linux-gnu'
task_kit='/d/yzd/WCIS/crosswin/kit'
export PATH="$task_tc/bin:/d/yzd/MSYS2/mingw64/bin:$PATH"
export CROSSWIN_TC="$(cygpath -m "$task_tc")"
task_opencv="$(cygpath -m "$task_kit/ModelzooDeps/aarch64/Static/lib/cmake/opencv4")"
cmake.exe -G Ninja -S "$(cygpath -m "$task_here")" -B "$(cygpath -m "$task_here/build")" \
  -DCMAKE_TOOLCHAIN_FILE=D:/yzd/WCIS/crosswin/cmake/crosswin-toolchain.cmake \
  -DCROSSWIN_TC="$CROSSWIN_TC" -DCMAKE_PREFIX_PATH="$(cygpath -m "$task_kit/cmake")" \
  -DOpenCV_DIR="$task_opencv" \
  -DCMAKE_POLICY_VERSION_MINIMUM=3.5 -DCMAKE_BUILD_TYPE=Release
cmake.exe --build "$(cygpath -m "$task_here/build")" -j2
"$task_tc/bin/aarch64-none-linux-gnu-readelf.exe" -h "$task_here/build/wcis_stream_demo" > "$task_here/build/elf-header.txt"
"$task_tc/bin/aarch64-none-linux-gnu-readelf.exe" -d "$task_here/build/wcis_stream_demo" > "$task_here/build/elf-dynamic.txt"
"$task_tc/bin/aarch64-none-linux-gnu-readelf.exe" -V "$task_here/build/wcis_stream_demo" > "$task_here/build/elf-versions.txt"
