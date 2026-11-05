"""One exclusive, bounded photo NPU run, preserving evidence and firmware."""
import json
import sys
from ssh_transport import board_connection, ROOT
sys.stdout.reconfigure(encoding='utf-8',errors='replace')
out=ROOT/'outputs/photo-board-20261014'
if (out/'board-staging.json').exists():
    raise RuntimeError('Deployment is incomplete; refusing to run the previous release')
release=json.loads((out/'board-staged-release.json').read_text(encoding='utf-8'))['release']
with board_connection() as client:
    # Guard the exact recorded factory process; do not kill by a broad name.
    stop='if pgrep -f "^./sdicamera" >/dev/null || pgrep -x wcis_face_npu >/dev/null; then echo NPU_OWNER_PRESENT; exit 4; fi; echo NPU_EXCLUSIVE'
    _,stdout,stderr=client.exec_command(stop,timeout=20)
    stopped={'stdout':stdout.read().decode(errors='replace'),'stderr':stderr.read().decode(errors='replace'),'exit':stdout.channel.recv_exit_status()}
    (out/'npu-exclusive-check.json').write_text(json.dumps(stopped,indent=2))
    print('factory stop',json.dumps(stopped),flush=True)
    assert stopped['exit']==0,stopped
    command='timeout --signal=TERM --kill-after=5s 300s python3 -u '+release+'/run_photos.py --out '+release+'/run-01 --run'
    _,stdout,_=client.exec_command(command,timeout=330)
    stdout.channel.set_combine_stderr(True)
    with (out/'board-npu-run.log').open('w',encoding='utf-8') as log:
        while True:
            chunk=stdout.channel.recv(8192)
            if not chunk:break
            value=chunk.decode(errors='replace');log.write(value);log.flush();print(value,end='',flush=True)
    code=stdout.channel.recv_exit_status();print('board exit',code,flush=True)
    s=client.open_sftp()
    for name in ('verification.json','failure.json','runner-stderr.log','runner-stdout.log'):
        try:s.get(release+'/run-01/'+name,str(out/('board-'+name)))
        except FileNotFoundError:pass
    _,o,e=client.exec_command('ps -eo pid,stat,comm,args | grep -E "wcis_face|sdicamera|run_photos"; free -m; dmesg | tail -10',timeout=20)
    health=o.read().decode(errors='replace')+e.read().decode(errors='replace')
    (out/'board-post-run.txt').write_text(health,encoding='utf-8');print(health,flush=True)
    (out/'board-run-status.json').write_text(json.dumps({'release':release,'exit_code':code,'factory_stopped':True,'automatic_retry':False},indent=2))
