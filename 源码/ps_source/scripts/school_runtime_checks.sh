#!/usr/bin/env bash
set -uo pipefail
task_here="$(cd -- "$(dirname -- "$0")" && pwd -P)"
case "$task_here" in /d/yzd/tmp/*) ;; *) exit 2;; esac
export TMP="$(cygpath -m "$task_here/scratch")"
export TEMP="$TMP" TMPDIR="$TMP" PYTHONDONTWRITEBYTECODE=1
export PYTHONPYCACHEPREFIX="$(cygpath -m "$task_here/cache/pycache")"
cd "$task_here"
for task_python in /d/yzd/qwen3/venv/Scripts/python.exe \
 /d/yzd/asr/onnx/env_export/Scripts/python.exe /d/yzd/asr/onnx/env_ort1.18/Scripts/python.exe \
 /d/yzd/asr/onnx/env_ortonly/Scripts/python.exe /d/yzd/asr/onnx/env_ort1.17/Scripts/python.exe; do
    printf 'RUNTIME_TEST %s\n' "$task_python"
    "$task_python" -B "$(cygpath -m "$task_here/python_runtime_probe.py")" "$(cygpath -m "$task_here/inventory")" 2>&1
    printf 'RUNTIME_PROCESS_EXIT=%s\n' "$?"
done
printf 'ADDITIONAL_TOOL_FILE_PATHS_READ_ONLY:\n'
for task_dir in /d/yzd/tools /d/yzd/WCIS/fdw /d/yzd/agenttmp/tools /d/yzd/.opencode; do
    [[ -d "$task_dir" ]] || continue
    find "$task_dir" -maxdepth 6 -type f \( -iname '*icraft*.exe' -o -iname '*ffmpeg*.exe' \
      -o -iname '*vivado*.bat' -o -iname '*procise*.exe' -o -iname '*iverilog*.exe' -o -iname '*verilator*.exe' \
      -o -iname '*readelf.exe' -o -iname '*g++.exe' \) | head -60
done
echo 'CPU RUNTIME CHECKS COMPLETE'
