#!/usr/bin/env bash
# Inventory metadata; never run project entrypoints or model/audio workloads.
set -uo pipefail
task_here="$(cd -- "$(dirname -- "$0")" && pwd -P)"
case "$task_here" in /d/yzd/tmp/*) ;; *) echo 'Unsafe inventory root'; exit 2;; esac
mkdir -p "$task_here/inventory" "$task_here/scratch" "$task_here/cache"
export TMP="$(cygpath -m "$task_here/scratch")"
export TEMP="$TMP" TMPDIR="$TMP" XDG_CACHE_HOME="$task_here/cache"
export PYTHONDONTWRITEBYTECODE=1 PYTHONPYCACHEPREFIX="$(cygpath -m "$task_here/cache/pycache")"
export PATH='/d/yzd/MSYS2/mingw64/bin:/usr/bin:'"$PATH"
cd "$task_here"
printf 'TOP_LEVEL_DIRECTORIES:\n'
find /d/yzd -maxdepth 2 -type d -not -path '/d/yzd/tmp/*' | sort > "$task_here/inventory/directories.txt"
cat "$task_here/inventory/directories.txt"
printf 'PYTHON_EXECUTABLES_AND_VENV_CONFIGS:\n'
find /d/yzd -maxdepth 5 -type f \( -iname 'python.exe' -o -iname 'python3.exe' -o -name 'pyvenv.cfg' \) \
  -not -path '/d/yzd/tmp/*' -not -path '*/site-packages/*' | sort > "$task_here/inventory/python-paths.txt"
cat "$task_here/inventory/python-paths.txt"
while IFS= read -r task_path; do
    if [[ "$task_path" == *.exe ]]; then
        printf 'PYTHON_PROBE %s\n' "$task_path"
        "$task_path" -B --version 2>&1
        printf 'PYTHON_VERSION_EXIT=%s\n' "$?"
        "$task_path" -B -c 'import sys,json,importlib.metadata as m; names=["pip","numpy","torch","onnx","onnxruntime","opencv-python","icraft","scipy","sounddevice","funasr"]; found={}; exec("for n in names:\n try: found[n]=m.version(n)\n except m.PackageNotFoundError: pass"); print(json.dumps({"executable":sys.executable,"prefix":sys.prefix,"installed_package_metadata":found,"packages_import_tested":False},ensure_ascii=True))' 2>&1
        printf 'PYTHON_METADATA_EXIT=%s\n' "$?"
    fi
done < "$task_here/inventory/python-paths.txt"
printf 'TOOLS_WITHIN_YZD:\n'
find /d/yzd -maxdepth 4 -type f \( -iname '*cmake*.exe' -o -iname '*ninja*.exe' -o -iname '*gcc.exe' -o -iname '*g++.exe' \
  -o -iname '*readelf.exe' -o -iname '*ffmpeg*.exe' -o -iname '*git.exe' -o -iname '*icraft*.exe' \
  -o -iname '*vivado*.bat' -o -iname '*procise*.exe' -o -iname '*verilator*.exe' -o -iname '*iverilog*.exe' \) \
  -not -path '/d/yzd/tmp/*' | sort > "$task_here/inventory/tools.txt"
cat "$task_here/inventory/tools.txt"
printf 'MAIN_TOOL_VERSION_PROBES:\n'
for task_tool in /d/yzd/MSYS2/mingw64/bin/cmake.exe /d/yzd/MSYS2/mingw64/bin/ninja.exe \
                 /d/yzd/MSYS2/usr/bin/bash.exe /d/yzd/MSYS2/usr/bin/git.exe; do
    [[ -f "$task_tool" ]] || continue
    printf 'TOOL_PROBE %s\n' "$task_tool"
    "$task_tool" --version 2>&1 | head -2
    printf 'TOOL_VERSION_EXIT=%s\n' "${PIPESTATUS[0]}"
done
printf 'SHARED_KIT_PACKAGE_VERSIONS_READ_ONLY:\n'
grep -H 'set(PACKAGE_VERSION' /d/yzd/WCIS/crosswin/kit/cmake/*config-version.cmake 2>/dev/null
printf 'READ_ONLY_MODEL_FILE_SAMPLES:\n'
find /d/yzd -maxdepth 4 -type f \( -name '*.onnx' -o -name '*.pt' -o -name '*.tflite' -o -name '*.task' \) \
  -not -path '/d/yzd/tmp/*' -not -path '*/site-packages/*' | head -70
echo 'INVENTORY COMPLETE; package metadata does not prove inference/deployment.'
