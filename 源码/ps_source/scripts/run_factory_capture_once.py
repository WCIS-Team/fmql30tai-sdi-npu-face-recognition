"""One finite real-camera frame after the factory SDK bridge probe passes.

Never resets the peripheral or retries. A failed attempt needs review before a
new capture token can be issued. Geometry is a 1080p trial, not auto-detection.
"""
from datetime import datetime, timezone
import hashlib
import json
import shlex
import urllib.request
import argparse
import re
from ssh_transport import ROOT, board_connection

parser=argparse.ArgumentParser()
parser.add_argument('--after-vtc',action='store_true',help='A distinct trial after a successful VTC test on a newer clean boot')
args=parser.parse_args()
out=ROOT/('outputs/camera-preview-final' if args.after_vtc else 'outputs/camera-preview-factory-capture-validated')
previous=out/('camera-after-vtc.json' if args.after_vtc else 'capture-once.json')
if previous.exists() and json.loads(previous.read_text()).get('capture_attempted'):
    raise SystemExit('Capture was already attempted. Review its evidence; no automatic retry.')
if args.after_vtc:
    bridge=json.loads((ROOT/'outputs/camera-preview-vtc-verification/path-check.json').read_text())
    assert bridge['path_test_passed'] and bridge['board_healthy_after_test'] and bridge['real_source_restored']
    old=json.loads((ROOT/'outputs/camera-preview-factory-capture-validated/capture-once.json').read_text())
    assert bridge['boot_id']!=old['expected_boot_id'], 'Do not retry the failed boot'
else:
    bridge=json.loads((ROOT/'outputs/camera-preview-factory/sdk-probe.json').read_text())
    assert bridge['bridge_verified'] and bridge['board_healthy_after_probe']
boot=bridge['boot_id']
binary=out/'wcis_camera_preview'
sha=hashlib.sha256(binary.read_bytes()).hexdigest()
assert sha==json.loads((out/'cross-build.json').read_text())['sha256']
release=json.loads((out/'deployment.json').read_text())['remote_directory'] if args.after_vtc else '/root/wcis-camera-preview/releases/'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')+'-'+sha[:12]
report={'remote_directory':release,'binary_sha256':sha,'expected_boot_id':boot,
        'capture_attempted':False,'max_frames':1,'models_loaded':False,'firmware_replaced':False,'reset_performed':False}
report['after_vtc_pass_on_new_boot']=args.after_vtc
def save():previous.write_text(json.dumps(report,indent=2),encoding='utf-8')
def run(c,cmd,timeout=8):
    _,o,e=c.exec_command(cmd,timeout=timeout)
    o.channel.set_combine_stderr(True)
    data=[]
    while True:
        b=o.channel.recv(8192)
        if not b:break
        data.append(b)
    return {'exit_code':o.channel.recv_exit_status(),'output':b''.join(data).decode(errors='replace')}

try:
    with board_connection() as c:
        identity=run(c,"python3 -c 'import json,time;print(json.dumps(dict(boot_id=open(\"/proc/sys/kernel/random/boot_id\").read().strip(),monotonic_us=time.monotonic_ns()//1000)))'")
        identity=json.loads(identity['output']);assert identity['boot_id']==boot
        assert not run(c,"ps -eo comm,args | grep -E '[w]cis_camera_preview|[w]cis_sdi_reference|[s]dicamera\\+yolov5' || true")['output'].strip()
        # Factory hash is rechecked independently of the earlier probe receipt.
        mount='/root/wcis-camera-preview/capture-check-ro'
        check='''set -eu
mkdir -p %s
test -z "$(findmnt -rn -S /dev/mmcblk0p1)"
mount -t vfat -o ro,nosuid,nodev,noexec /dev/mmcblk0p1 %s
trap 'umount %s' EXIT
sha256sum %s/BOOT.bin
''' % (mount,mount,mount,mount)
        assert run(c,'sh -c '+shlex.quote(check))['output'].split()[0]=='0088581b738fdef741983d2dfd4dd52363d2d90fddc2fa4dafb30cfdb3b23fca'
        s=c.open_sftp()
        if not args.after_vtc:
            s.mkdir(release)
            s.put(str(binary),release+'/wcis_camera_preview');s.chmod(release+'/wcis_camera_preview',0o700)
        config=(ROOT/'ps_app/configs/camera-preview.yaml').read_text()
        config=config.replace('run_seconds: 30','run_seconds: 3\nmax_frames: 1')
        with s.open(release+'/single-frame.yaml','w') as f:f.write(config)
        assert run(c,'sha256sum '+release+'/wcis_camera_preview')['output'].split()[0]==sha
        assert run(c,release+'/wcis_camera_preview '+release+'/single-frame.yaml 192.168.1.106')['exit_code']==0
        gate=dict(schema_version=1,boot_id=boot,boot_sha256='0088581b738fdef741983d2dfd4dd52363d2d90fddc2fa4dafb30cfdb3b23fca',
                  expires_monotonic_us=identity['monotonic_us']+90000000,sdk_probe_permitted=True,capture_permitted=True)
        if args.after_vtc:
            with s.open(release+'/inspection-only.json','w') as f:f.write(json.dumps(dict(gate,capture_permitted=False)))
            inspect=run(c,'timeout 10s '+release+'/wcis_camera_preview '+release+'/single-frame.yaml 192.168.1.106 --inspect-camera --attestation '+release+'/inspection-only.json',timeout=14)
            assert inspect['exit_code']==0
            state=json.loads(re.findall(r'SDK_PROBE (\{[^\r\n]*\})',inspect['output'])[0])
            assert state['registers']['vtc_enable']==0 and state['registers']['request_pending']==0 and state['capture_status']&4==0
            report['before_capture_registers']=state
        with s.open(release+'/capture-attestation.json','w') as f:f.write(json.dumps(gate))
        s.close()
        state=json.load(urllib.request.urlopen('http://127.0.0.1:8088/api/status',timeout=3))
        report['receiver_frames_before']=state['frames_received']
        report['capture_attempted']=True;save()
        trial=run(c,'timeout --signal=TERM --kill-after=2s 12s '+release+'/wcis_camera_preview '+release+'/single-frame.yaml 192.168.1.106 --run-camera --attestation '+release+'/capture-attestation.json',timeout=18)
        report['trial']=trial
        (out/'capture-once.log').write_text(trial['output'],encoding='utf-8')
        print(trial['output'],flush=True);save()
        report['after_trial']=run(c,'cat /proc/sys/kernel/random/boot_id; uptime; tail -n 3 /var/log/wcis-heartbeat/heartbeat.log')
        assert boot in report['after_trial']['output']
        report['board_healthy_after_trial']=True
        state=json.load(urllib.request.urlopen('http://127.0.0.1:8088/api/status',timeout=3))
        report['receiver_frames_after']=state['frames_received']
        report['camera_frame_received']=trial['exit_code']==0 and state['frames_received']>report['receiver_frames_before']
        if trial['exit_code']!=0:
            note=json.dumps({'boot_id':boot,'reason':'single-frame trial failed; pending peripheral state needs review','no_automatic_retry':True},indent=2)
            with c.open_sftp() as s:
                with s.open(release+'/CAPTURE_REVIEW_REQUIRED.json','w') as f:f.write(note)
    print(json.dumps(report,indent=2),flush=True)
except Exception as error:
    report['error_type']=type(error).__name__;raise
finally:save()
