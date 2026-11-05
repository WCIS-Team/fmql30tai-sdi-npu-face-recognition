"""Isolated school-server cross-build, never build a model or access hardware."""
import hashlib
import json
from pathlib import Path
import sys
import tarfile
import uuid
from school_connection import school_connection, ROOT


def main():
    out=Path('D:/yzd/tmp/face-pl-integration-20261015/school-build')
    out.mkdir(parents=True,exist_ok=True)
    task='/D:/yzd/tmp/wcis-face-pl-20261015-'+uuid.uuid4().hex[:8]
    archive=out/'npu-source.tar.gz'
    with tarfile.open(archive,'w:gz') as tar:
        for relative in ['npu_photo/CMakeLists.txt','npu_photo/src','npu_photo/vendor']:
            tar.add(ROOT/relative,arcname=relative)
    receipt=dict(task=task,archive_sha256=hashlib.sha256(archive.read_bytes()).hexdigest(),
        model_recompiled=False,board_accessed=False)
    with school_connection() as client:
        sftp=client.open_sftp();sftp.mkdir(task)
        sftp.put(str(archive),task+'/npu-source.tar.gz')
        sftp.put(str(ROOT/'scripts/build_face_npu_school.sh'),task+'/build.sh')
        _,stdout,_=client.exec_command('D:/yzd/MSYS2/usr/bin/bash.exe --login '+task.lstrip('/')+'/build.sh',timeout=180)
        stdout.channel.set_combine_stderr(True)
        with (out/'build.log').open('wb') as log:
            while True:
                block=stdout.channel.recv(8192)
                if not block:break
                log.write(block);log.flush();print(block.decode(errors='replace'),end='',flush=True)
        receipt['exit']=stdout.channel.recv_exit_status()
        if receipt['exit']==0:
            local=out/'wcis_face_pl';sftp.get(task+'/npu-build/wcis_face_pl',str(local))
            receipt['executable_sha256']=hashlib.sha256(local.read_bytes()).hexdigest()
    (out/'build-receipt.json').write_text(json.dumps(receipt,indent=2)+'\n')
    if receipt['exit']:raise SystemExit(receipt['exit'])


if __name__=='__main__':main()
