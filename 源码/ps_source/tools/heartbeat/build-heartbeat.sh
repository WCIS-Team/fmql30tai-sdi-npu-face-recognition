#!/usr/bin/env bash
set -euo pipefail
task_here="$(cd -- "$(dirname -- "$0")" && pwd -P)"
case "$task_here" in /d/yzd/tmp/*) ;; *) exit 2;; esac
export TMP="$(cygpath -m "$task_here/scratch")" TEMP="$(cygpath -m "$task_here/scratch")" TMPDIR="$(cygpath -m "$task_here/scratch")"
mkdir -p "$task_here/scratch"
task_tc='/d/yzd/tools/cross/gcc-arm-10.3-2021.07-mingw-w64-i686-aarch64-none-linux-gnu'
"$task_tc/bin/aarch64-none-linux-gnu-gcc.exe" -static -s -std=c11 -Os -Wall -Wextra -Werror -fstack-protector-strong -Wl,-z,relro,-z,now -o "$(cygpath -m "$task_here/wcis-heartbeat")" "$(cygpath -m "$task_here/wcis-heartbeat.c")"
"$task_tc/bin/aarch64-none-linux-gnu-readelf.exe" -h "$task_here/wcis-heartbeat"
sha256sum "$task_here/wcis-heartbeat"

