"""Restore the verified factory BOOT, only with explicit --apply --reboot.

User approved this specific switch on 2026-10-14. Preserve both local and SD
backups, reject a changed starting image, and verify after writes before reboot.
No SDK, MMIO, camera or model is opened by this script.
"""
import argparse
from datetime import datetime, timezone
import hashlib
import json
import shlex
import uuid
from ssh_transport import ROOT, board_connection

EXPECTED_OLD = '6e81a17a9fb429607b619c653598d4c260c9d820b835e583d8e87bfb6532cb85'
EXPECTED_FACTORY = '0088581b738fdef741983d2dfd4dd52363d2d90fddc2fa4dafb30cfdb3b23fca'

# This script runs only in the uploaded, task-owned staging directory.
REMOTE = r'''
import hashlib, json, os, signal, shutil, subprocess, time
from pathlib import Path

here=Path(__file__).resolve().parent
assert here.parent == Path('/root/wcis-camera-preview/boot-restores')
mount=here/'sd-boot'
candidate=here/'BOOT.factory-candidate.bin'
old='6e81a17a9fb429607b619c653598d4c260c9d820b835e583d8e87bfb6532cb85'
new='0088581b738fdef741983d2dfd4dd52363d2d90fddc2fa4dafb30cfdb3b23fca'
def sha(p): return hashlib.sha256(p.read_bytes()).hexdigest()
def save():
    (here/'receipt.json').write_text(json.dumps(report,indent=2))
    print(json.dumps(report),flush=True)
def copy_sync(src,dst):
    with src.open('rb') as rd, dst.open('xb') as wr:
        shutil.copyfileobj(rd,wr)
        wr.flush();os.fsync(wr.fileno())

report={'factory_sha256':new,'firmware_replaced':False,'reboot_requested':False}
assert sha(candidate)==new
# Stop only our own DDR diagnostic sender, after PID, working directory and command checks.
pidfile=Path('/root/wcis-camera-preview/status-20261014/status.pid')
if pidfile.exists():
    pid=int(pidfile.read_text())
    proc=Path('/proc')/str(pid)
    if proc.exists():
        command=(proc/'cmdline').read_bytes().replace(b'\0',b' ').decode()
        cwd=(proc/'cwd').resolve()
        if cwd!=pidfile.parent or 'sdi_status_sender.py' not in command:
            raise RuntimeError('Diagnostic PID ownership changed')
        os.kill(pid,signal.SIGTERM)
        report['stopped_status_pid']=pid
        for _ in range(30):
            if not proc.exists():break
            time.sleep(.1)
        if proc.exists():
            raise RuntimeError('Diagnostic sender did not stop; refusing boot switch')
if subprocess.run(['findmnt','-rn','-S','/dev/mmcblk0p1'],capture_output=True).stdout.strip():
    raise RuntimeError('Boot partition already mounted by another task')
mount.mkdir()
subprocess.run(['mount','-t','vfat','-o','rw,nosuid,nodev,noexec','/dev/mmcblk0p1',str(mount)],check=True)
boot=mount/'BOOT.bin'
backup=mount/('BOOT.before_factory_'+here.name+'.bin')
pending=mount/('BOOT.pending_'+here.name+'.bin')
changed=False
try:
    report['initial_boot_sha256']=sha(boot)
    assert report['initial_boot_sha256']==old, 'Starting BOOT changed; refusing replacement'
    assert sha(mount/'BOOT.bak')==new, 'Factory backup identity changed'
    copy_sync(boot,backup)
    assert sha(backup)==old
    report['sd_backup_name']=backup.name
    copy_sync(candidate,pending)
    assert sha(pending)==new
    os.replace(pending,boot);changed=True
    os.sync()
    assert sha(boot)==new
    report['firmware_replaced']=True
    report['final_boot_sha256']=sha(boot)
    report['backup_sha256']=sha(backup)
    save()
except BaseException as error:
    report['error_type']=type(error).__name__
    if changed:
        rollback=mount/('BOOT.rollback_'+here.name+'.bin')
        copy_sync(backup,rollback)
        assert sha(rollback)==old
        os.replace(rollback,boot);os.sync()
        report['rolled_back']=sha(boot)==old
        report['firmware_replaced']=not report['rolled_back']
    save()
    raise
finally:
    subprocess.run(['umount',str(mount)],check=True)
report['boot_partition_unmounted']=True
save()
'''


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--apply',action='store_true')
    parser.add_argument('--reboot',action='store_true')
    args=parser.parse_args()
    source=ROOT/'outputs/camera-preview/boot-recovery-prepared'
    candidate=source/'BOOT.factory-candidate.bin'
    backup=source/'BOOT.current-backup.bin'
    assert hashlib.sha256(candidate.read_bytes()).hexdigest()==EXPECTED_FACTORY
    assert hashlib.sha256(backup.read_bytes()).hexdigest()==EXPECTED_OLD
    if not(args.apply and args.reboot):
        raise SystemExit('Files validated. No board operation. Authorized switch requires --apply --reboot together.')
    tag=datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')+'-'+uuid.uuid4().hex[:8]
    staging='/root/wcis-camera-preview/boot-restores/'+tag
    out=ROOT/'outputs/camera-preview/factory-restore.json'
    report={'authorized_by_user':True,'remote_directory':staging,'firmware_replaced':False,'reboot_requested':False}
    try:
        with board_connection() as client:
            sftp=client.open_sftp()
            try:sftp.mkdir('/root/wcis-camera-preview/boot-restores')
            except IOError:sftp.stat('/root/wcis-camera-preview/boot-restores')
            sftp.mkdir(staging)
            sftp.put(str(candidate),staging+'/BOOT.factory-candidate.bin')
            with sftp.open(staging+'/restore.py','w') as handle:handle.write(REMOTE)
            _,stdout,stderr=client.exec_command('python3 '+shlex.quote(staging+'/restore.py'),timeout=30)
            stdout.channel.set_combine_stderr(True)
            parts=[]
            while True:
                data=stdout.channel.recv(8192)
                if not data:break
                parts.append(data);print(data.decode(errors='replace'),end='',flush=True)
            report['restore_exit_code']=stdout.channel.recv_exit_status()
            report['restore_log']=b''.join(parts).decode(errors='replace')
            with sftp.open(staging+'/receipt.json','r') as handle:receipt=json.load(handle)
            report.update(receipt)
            assert report['restore_exit_code']==0 and report['firmware_replaced'] and report['boot_partition_unmounted']
            _,stdout,stderr=client.exec_command('cat /proc/sys/kernel/random/boot_id',timeout=4)
            report['previous_boot_id']=stdout.read().decode().strip()
            assert stdout.channel.recv_exit_status()==0
            # Store evidence before a connection-ending action.
            out.write_text(json.dumps(report,indent=2),encoding='utf-8')
            sftp.close()
            report['reboot_requested']=True
            out.write_text(json.dumps(report,indent=2),encoding='utf-8')
            client.exec_command('systemctl reboot',timeout=5)
            print('Verified BOOT restored; reboot requested.',flush=True)
    except Exception as error:
        report['error_type']=type(error).__name__
        raise
    finally:
        out.write_text(json.dumps(report,indent=2),encoding='utf-8')


if __name__=='__main__':main()
