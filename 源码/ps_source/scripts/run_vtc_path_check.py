"""One labelled hardware test frame after a clean factory boot; no camera retry."""
from datetime import datetime, timezone
import hashlib
import json
import re
import shlex
import struct
import threading
import time
import urllib.error
import urllib.request
from ssh_transport import ROOT, board_connection

out=ROOT/'outputs/camera-preview-vtc-verification'
result=out/'path-check.json'
if result.exists() and json.loads(result.read_text()).get('test_capture_attempted'):
    raise SystemExit('The VTC test was already attempted; inspect its result, do not retry automatically.')
binary=out/'wcis_camera_preview'
sha=hashlib.sha256(binary.read_bytes()).hexdigest()
assert sha==json.loads((out/'cross-build.json').read_text())['sha256']
release='/root/wcis-camera-preview/releases/'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')+'-'+sha[:12]
report={'remote_directory':release,'binary_sha256':sha,'test_capture_attempted':False,'real_camera_capture_attempted':False,'models_loaded':False,'firmware_replaced':False}
def save():result.write_text(json.dumps(report,indent=2),encoding='utf-8')
def run(c,name,cmd,timeout=8):
    _,o,e=c.exec_command(cmd,timeout=timeout);o.channel.set_combine_stderr(True)
    text=o.read().decode(errors='replace')
    reply={'exit_code':o.channel.recv_exit_status(),'output':text}
    report[name]=reply;save();print(name+':\n'+text,flush=True)
    return reply
packet=[]
halt=threading.Event()
def observe():
    while not halt.is_set():
        try:
            with urllib.request.urlopen('http://127.0.0.1:8088/api/frame',timeout=.4) as reply:
                data=reply.read()
            size=struct.unpack_from('!I',data)[0];meta=json.loads(data[4:4+size])
            if meta['source']=='demo' and meta['stream_id'].startswith('vtc-'):
                packet.append(data);(out/'test-frame.packet').write_bytes(data)
                (out/'test-frame-metadata.json').write_text(json.dumps(meta,indent=2),encoding='utf-8')
                return
        except (urllib.error.URLError,ValueError,OSError):pass
        halt.wait(.05)

try:
    with board_connection() as c:
        identity=run(c,'identity',"python3 -c 'import json,time;print(json.dumps(dict(boot_id=open(\"/proc/sys/kernel/random/boot_id\").read().strip(),monotonic_us=time.monotonic_ns()//1000)))'")
        identity=json.loads(identity['output']);report['boot_id']=identity['boot_id']
        previous=json.loads((out/'clean-reboot.json').read_text())['previous_boot_id']
        assert identity['boot_id']!=previous
        check='''set -eu
p=/root/wcis-camera-preview/vtc-check-ro
mkdir -p "$p"
test -z "$(findmnt -rn -S /dev/mmcblk0p1)"
mount -t vfat -o ro,nosuid,nodev,noexec /dev/mmcblk0p1 "$p"
trap 'umount "$p"' EXIT
sha256sum "$p"/BOOT.bin
'''
        assert run(c,'boot_identity','sh -c '+shlex.quote(check))['output'].split()[0]=='0088581b738fdef741983d2dfd4dd52363d2d90fddc2fa4dafb30cfdb3b23fca'
        assert not run(c,'existing_captures',"ps -eo comm,args | grep -E '[w]cis_camera_preview|[w]cis_sdi_reference|[s]dicamera\\+yolov5' || true")['output'].strip()
        s=c.open_sftp();s.mkdir(release);s.put(str(binary),release+'/wcis_camera_preview');s.chmod(release+'/wcis_camera_preview',0o700)
        config=(ROOT/'ps_app/configs/camera-preview.yaml').read_text().replace('vtc: false','vtc: true').replace('run_seconds: 30','run_seconds: 3\nmax_frames: 1')
        with s.open(release+'/vtc-test.yaml','w') as f:f.write(config)
        gate=dict(schema_version=1,boot_id=identity['boot_id'],boot_sha256='0088581b738fdef741983d2dfd4dd52363d2d90fddc2fa4dafb30cfdb3b23fca',expires_monotonic_us=identity['monotonic_us']+90000000,sdk_probe_permitted=True,capture_permitted=False)
        with s.open(release+'/probe.json','w') as f:f.write(json.dumps(gate))
        assert run(c,'binary_identity','sha256sum '+release+'/wcis_camera_preview')['output'].split()[0]==sha
        probe=run(c,'bridge_probe','timeout 10s '+release+'/wcis_camera_preview '+release+'/vtc-test.yaml 192.168.1.106 --inspect-camera --attestation '+release+'/probe.json',timeout=14)
        assert probe['exit_code']==0
        evidence=json.loads(re.findall(r'SDK_PROBE (\{[^\r\n]*\})',probe['output'])[0])
        assert evidence['version']==0x20230218 and evidence['capture_status']==0 and evidence['registers']['fetch_count']==0
        report['fresh_bridge_verified']=True
        gate['capture_permitted']=True
        with s.open(release+'/test-once.json','w') as f:f.write(json.dumps(gate))
        s.close()
        watcher=threading.Thread(target=observe,daemon=True);watcher.start()
        report['test_capture_attempted']=True;save()
        try:
            trial=run(c,'test_capture','timeout --signal=TERM --kill-after=2s 12s '+release+'/wcis_camera_preview '+release+'/vtc-test.yaml 192.168.1.106 --run-vtc-test --attestation '+release+'/test-once.json',timeout=18)
            halt.wait(.25)
        finally:
            halt.set();watcher.join(1)
        report['test_packet_received']=bool(packet)
        if packet:report['packet_sha256']=hashlib.sha256(packet[0]).hexdigest()
        report['path_test_passed']=trial['exit_code']==0 and bool(packet)
        report['after_test']=run(c,'health','cat /proc/sys/kernel/random/boot_id; uptime; tail -n 3 /var/log/wcis-heartbeat/heartbeat.log')
        assert identity['boot_id'] in report['after_test']['output'];report['board_healthy_after_test']=True
        # Only inspect documented state, without requesting another capture.
        report['source_after_test']=run(c,'source_after_test','timeout 10s '+release+'/wcis_camera_preview '+release+'/vtc-test.yaml 192.168.1.106 --inspect-camera --attestation '+release+'/probe.json',timeout=14)
        if report['path_test_passed']:
            after=json.loads(re.findall(r'SDK_PROBE (\{[^\r\n]*\})',report['source_after_test']['output'])[0])
            assert after['registers']['vtc_enable']==0
            report['real_source_restored']=True
    print(json.dumps(report,indent=2),flush=True)
except Exception as error:
    report['error_type']=type(error).__name__;raise
finally:save()
