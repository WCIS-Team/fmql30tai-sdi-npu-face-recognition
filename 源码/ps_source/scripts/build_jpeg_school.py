"""Cross-build the JPEG SDK client in an isolated school-server task."""
import hashlib,json,sys,tarfile,uuid
from pathlib import Path
from school_connection import school_connection,ROOT
OUT=Path('D:/yzd/tmp/pl-jpeg-board-20261016/school-build')
BUILD=r'''#!/usr/bin/env bash
set -euo pipefail
task_here="$(cd -- "$(dirname -- "$0")" && pwd -P)"
case "$task_here" in /d/yzd/tmp/wcis-face-jpeg-*) ;; *) exit 2;; esac
mkdir -p "$task_here/scratch" "$task_here/cache"
export TMP="$(cygpath -m "$task_here/scratch")" TEMP="$(cygpath -m "$task_here/scratch")" TMPDIR="$(cygpath -m "$task_here/scratch")"
export XDG_CACHE_HOME="$task_here/cache" MSYS2_ARG_CONV_EXCL='*'
export PATH="/d/yzd/tools/cross/gcc-arm-10.3-2021.07-mingw-w64-i686-aarch64-none-linux-gnu/bin:/d/yzd/MSYS2/mingw64/bin:$PATH"
task_tc='D:/yzd/tools/cross/gcc-arm-10.3-2021.07-mingw-w64-i686-aarch64-none-linux-gnu'
export CROSSWIN_TC="$task_tc"
cd "$task_here"
cmake.exe --version
"$task_tc/bin/aarch64-none-linux-gnu-g++.exe" --version
tar -xzf source.tar.gz
cmake.exe -G Ninja -S "$(cygpath -m "$task_here/npu_photo")" -B "$(cygpath -m "$task_here/build")" \
 -DCMAKE_TOOLCHAIN_FILE=D:/yzd/WCIS/crosswin/cmake/crosswin-toolchain.cmake \
 -DCROSSWIN_TC="$task_tc" -DCMAKE_PREFIX_PATH=D:/yzd/WCIS/crosswin/kit/cmake \
 -DWCIS_UAPI_ROOT=D:/yzd/WCIS/crosswin/uapi -DCMAKE_POLICY_VERSION_MINIMUM=3.5 -DCMAKE_BUILD_TYPE=Release
cmake.exe --build "$(cygpath -m "$task_here/build")" --target wcis_jpeg -j2
"$task_tc/bin/aarch64-none-linux-gnu-readelf.exe" -h "$(cygpath -m "$task_here/build/wcis_jpeg")" > "$task_here/build/elf-header.txt"
"$task_tc/bin/aarch64-none-linux-gnu-readelf.exe" -d "$(cygpath -m "$task_here/build/wcis_jpeg")" > "$task_here/build/elf-dynamic.txt"
'''
def main():
    OUT.mkdir(parents=True,exist_ok=True)
    task='/D:/yzd/tmp/wcis-face-jpeg-'+uuid.uuid4().hex[:10]
    archive=OUT/'source.tar.gz'
    with tarfile.open(archive,'w:gz') as tar:
        for path in ('npu_photo/CMakeLists.txt','npu_photo/src','npu_photo/vendor'):
            tar.add(ROOT/path,arcname=path)
    receipt=dict(task=task,source_sha256=hashlib.sha256(archive.read_bytes()).hexdigest(),model_built=False,board_accessed=False)
    with school_connection() as c:
        # Inspect tool availability/current compiler work before starting ours.
        _,out,err=c.exec_command('powershell.exe -NoProfile -Command "Get-Process cc1plus,cmake,ninja -ErrorAction SilentlyContinue | Select-Object ProcessName,Id; Test-Path D:/yzd/WCIS/crosswin/kit/cmake; Test-Path D:/yzd/MSYS2/usr/bin/bash.exe"',timeout=25)
        (OUT/'preflight.txt').write_bytes(out.read()+err.read())
        s=c.open_sftp();s.mkdir(task);s.put(str(archive),task+'/source.tar.gz')
        with s.open(task+'/build.sh','wb') as f:f.write(BUILD.encode())
        _,out,_=c.exec_command('D:/yzd/MSYS2/usr/bin/bash.exe --login '+task.lstrip('/')+'/build.sh',timeout=180)
        out.channel.set_combine_stderr(True)
        with (OUT/'build.log').open('wb') as log:
            while True:
                b=out.channel.recv(8192)
                if not b:break
                log.write(b);log.flush()
        receipt['exit']=out.channel.recv_exit_status()
        if not receipt['exit']:
            for name in ('wcis_jpeg','elf-header.txt','elf-dynamic.txt'):
                s.get(task+'/build/'+name,str(OUT/name))
            receipt['binary_sha256']=hashlib.sha256((OUT/'wcis_jpeg').read_bytes()).hexdigest()
    (OUT/'receipt.json').write_text(json.dumps(receipt,indent=2))
    print(json.dumps(receipt,indent=2),flush=True)
    if receipt['exit']:
        print((OUT/'build.log').read_text(errors='replace')[-5000:]);raise SystemExit(receipt['exit'])
if __name__=='__main__':main()
