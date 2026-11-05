"""Cross-build only the NTP2 manager, isolated on the school server."""
from pathlib import Path
import argparse,hashlib,json,tarfile,uuid
from school_connection import school_connection,ROOT
from build_jpeg_school import BUILD

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out',type=Path,required=True);args=parser.parse_args()
    out=args.out.resolve();out.mkdir(parents=True,exist_ok=True)
    remote='/D:/yzd/tmp/wcis-pl-net-20261024-'+uuid.uuid4().hex[:10]
    script=BUILD.replace('/d/yzd/tmp/wcis-face-jpeg-*','/d/yzd/tmp/wcis-pl-net-20261024-*').replace('wcis_jpeg','wcis_pl_net_config')
    archive=out/'source.tar.gz'
    with tarfile.open(archive,'w:gz') as tar:
        for name in ('npu_photo/CMakeLists.txt','npu_photo/src','npu_photo/vendor'):tar.add(ROOT/name,arcname=name)
    receipt=dict(remote_directory=remote,built=False,board_accessed=False,model_compiled=False,
        source_sha256=hashlib.sha256(archive.read_bytes()).hexdigest(),
        manager_source_sha256=hashlib.sha256((ROOT/'npu_photo/src/pl_net_config.cpp').read_bytes()).hexdigest())
    try:
        with school_connection() as client:
            command='powershell.exe -NoProfile -Command "Get-Process cc1plus,cmake,ninja -ErrorAction SilentlyContinue | Select-Object ProcessName,Id; Test-Path D:/yzd/WCIS/crosswin/kit/cmake; Test-Path D:/yzd/MSYS2/usr/bin/bash.exe; Test-Path D:/yzd/tools/cross/gcc-arm-10.3-2021.07-mingw-w64-i686-aarch64-none-linux-gnu/bin/aarch64-none-linux-gnu-g++.exe"'
            _,o,e=client.exec_command(command,timeout=25);preflight=o.read()+e.read()
            (out/'preflight.txt').write_bytes(preflight)
            if preflight.decode(errors='replace').split().count('True')!=3:raise RuntimeError('Required school tools unavailable')
            with client.open_sftp() as s:
                s.mkdir(remote);s.put(str(archive),remote+'/source.tar.gz')
                with s.open(remote+'/build.sh','wb') as f:f.write(script.encode())
            _,o,_=client.exec_command('D:/yzd/MSYS2/usr/bin/bash.exe --login '+remote.lstrip('/')+'/build.sh',timeout=240)
            o.channel.set_combine_stderr(True)
            with (out/'build.log').open('wb') as log:
                while True:
                    data=o.channel.recv(8192)
                    if not data:break
                    log.write(data);log.flush()
            receipt['exit_code']=o.channel.recv_exit_status()
            if not receipt['exit_code']:
                with client.open_sftp() as s:
                    for name in ('wcis_pl_net_config','elf-header.txt','elf-dynamic.txt'):s.get(remote+'/build/'+name,str(out/name))
                receipt['built']=True
                receipt['binary_sha256']=hashlib.sha256((out/'wcis_pl_net_config').read_bytes()).hexdigest()
    except Exception as error:
        receipt['error_type']=type(error).__name__
    (out/'receipt.json').write_text(json.dumps(receipt,indent=2))
    print(json.dumps(receipt,indent=2))
    return 0 if receipt['built'] else 1
if __name__=='__main__':raise SystemExit(main())
