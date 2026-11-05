"""Deploy a reviewed JPEG BOOT trial, preserving current PS/DTB and rollback."""
import argparse,hashlib,json,re
from pathlib import Path
from ssh_transport import ROOT,board_connection
TASK=Path('D:/yzd/tmp/pl-jpeg-board-20261016')
REMOTE='/root/wcis-face/candidates/jpeg-20261016'
def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--retry-from-rollback',action='store_true',help='Require a completed rollback before another reviewed trial')
    args=p.parse_args()
    proof=json.loads((TASK/'boot-candidate/manifest.json').read_text())
    gate=json.loads((TASK/'timing-gate.json').read_text())
    before=json.loads((TASK/'board-before.json').read_text())
    regression=json.loads((TASK/'face-regression/verification.json').read_text())
    jpeg=json.loads((TASK/'verification/summary.json').read_text())
    assert proof['ps_partitions_identical'] and proof['current_bit_payload_matches']
    assert gate['setup_wns']>=0 and gate['hold_whs']>=0
    assert len(regression['cases'])==6 and all(c['passed'] for c in regression['cases'])
    assert len(jpeg['cases'])==2 and all(c['passed'] for c in jpeg['cases'])
    # Bind the actually tested RTL to the build's staged files.
    for name in ('wcis_recording_customop.v','wcis_jpeg_customop.v','wcis_jpeg_compressor.v','wcis_face_customop.v'):
        source=ROOT/'rtl'/name;staged=TASK/'case/rtl/wcis'/name
        assert source.read_bytes()==staged.read_bytes(),name
    cfg=dict(boot_id_before=before['boot_id'],release=before['root'],
        old_sha256=before['boot_files']['BOOT.bin']['sha256'],new_sha256=proof['boot_sha256'],
        dtb_sha256=before['boot_files']['fmqlmp-verify.dtb']['sha256'],uenv_sha256=before['boot_files']['uEnv.txt']['sha256'],
        photo_service_sha256=before['photo_service_sha256'],ps_partitions_identical=True)
    (TASK/'deploy.json').write_text(json.dumps(cfg,indent=2))
    service='[Unit]\nDescription=Recover unaccepted JPEG firmware trial\nAfter=network-online.target\n[Service]\nType=oneshot\nExecStart=/usr/bin/python3 '+REMOTE+'/jpeg_boot_remote.py --recover\n'
    timer='[Unit]\nDescription=Bounded JPEG firmware trial recovery\n[Timer]\nOnBootSec=240\nAccuracySec=1\nUnit=wcis-jpeg-trial-20261016.service\n[Install]\nWantedBy=timers.target\n'
    with board_connection() as c:
        s=c.open_sftp()
        if args.retry_from_rollback:
            with s.open(REMOTE+'/recovery.json','rb') as f:recovery=json.loads(f.read())
            assert recovery['rollback']
            with s.open('/proc/sys/kernel/random/boot_id','rb') as f:boot=f.read().decode().strip()
            assert boot not in (recovery['boot_id'],before['boot_id'])
            _,out,err=c.exec_command('systemctl is-enabled wcis-jpeg-trial-20261016.timer',timeout=10)
            assert out.read().decode().strip()=='disabled',err.read().decode()
            # jpeg_boot_remote still checks the old BOOT/DTB/uEnv hashes before
            # mutation. Preserve the original pre-task snapshot and prior trial.
            cfg['boot_id_before']=boot
            (TASK/'deploy.json').write_text(json.dumps(cfg,indent=2))
        for src,dest in [(TASK/'boot-candidate/BOOT.bin','candidate-BOOT.bin'),(TASK/'deploy.json','deploy.json'),
                         (ROOT/'scripts/jpeg_boot_remote.py','jpeg_boot_remote.py')]:
            s.put(str(src),REMOTE+'/'+dest)
            with s.open(REMOTE+'/'+dest,'rb') as f:assert hashlib.sha256(f.read()).digest()==hashlib.sha256(src.read_bytes()).digest()
        for suffix,value in [('service',service),('timer',timer)]:
            dest='/etc/systemd/system/wcis-jpeg-trial-20261016.'+suffix
            try:
                with s.open(dest,'rb') as f:old=f.read()
                assert old==value.encode(),'Recovery unit belongs to another setup'
            except FileNotFoundError:
                with s.open(dest,'wb') as f:f.write(value.encode())
        _,out,err=c.exec_command('python3 '+REMOTE+'/jpeg_boot_remote.py',timeout=100)
        data=out.read();error=err.read();(TASK/'deployment.log').write_bytes(data+error)
        if out.channel.recv_exit_status():raise RuntimeError(error.decode())
        report=json.loads(data);assert report['firmware_replaced']
        (TASK/'deployment.json').write_text(json.dumps(report,indent=2))
        c.exec_command('systemctl reboot',timeout=5)
        print('Reviewed JPEG firmware installed; normal reboot requested; rollback armed.',flush=True)
if __name__=='__main__':main()
