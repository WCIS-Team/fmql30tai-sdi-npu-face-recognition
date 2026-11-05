"""Deploy the gated adapter and probe only after the factory BOOT is rechecked.

Negative gate checks do not open a device. --run-probe permits one SDK open and
two documented register reads, with no camera constructor or capture request.
"""
import argparse
from datetime import datetime, timezone
import hashlib
import json
import re
import shlex
import time
from ssh_transport import ROOT, board_connection

FACTORY_SHA='0088581b738fdef741983d2dfd4dd52363d2d90fddc2fa4dafb30cfdb3b23fca'


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--run-probe',action='store_true')
    args=parser.parse_args()
    out=ROOT/'outputs/camera-preview-factory'
    binary=out/'wcis_camera_preview'
    sha=hashlib.sha256(binary.read_bytes()).hexdigest()
    assert sha==json.loads((out/'cross-build.json').read_text())['sha256']
    result_path=out/'sdk-probe.json'
    if result_path.exists() and json.loads(result_path.read_text()).get('hardware_probe_attempted'):
        raise SystemExit('A probe was already attempted. Review its result; no automatic hardware retry.')
    release='/root/wcis-camera-preview/releases/'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')+'-'+sha[:12]
    report={'remote_directory':release,'binary_sha256':sha,'hardware_probe_attempted':False,'camera_configured':False,'firmware_replaced':False}
    def save():result_path.write_text(json.dumps(report,indent=2),encoding='utf-8')
    def run(c,name,cmd,timeout=8):
        _,stdout,stderr=c.exec_command(cmd,timeout=timeout)
        stdout.channel.set_combine_stderr(True)
        parts=[]
        while True:
            data=stdout.channel.recv(8192)
            if not data:break
            parts.append(data)
        value=b''.join(parts).decode(errors='replace')
        result={'exit_code':stdout.channel.recv_exit_status(),'output':value}
        report[name]=result;save();print(name+': '+value,flush=True)
        return result
    try:
        with board_connection() as c:
            identity=run(c,'identity',"python3 -c 'import json,time;print(json.dumps(dict(boot_id=open(\"/proc/sys/kernel/random/boot_id\").read().strip(),monotonic_us=time.monotonic_ns()//1000)))'")
            identity=json.loads(identity['output'])
            report['boot_id']=identity['boot_id']
            known=json.loads((ROOT/'outputs/camera-preview/factory-reboot-verification.json').read_text())
            assert identity['boot_id']==known['new_boot_id']
            check=r'''set -eu
p=/root/wcis-camera-preview/factory-sdk-check-ro
mkdir -p "$p"
test -z "$(findmnt -rn -S /dev/mmcblk0p1)"
mount -t vfat -o ro,nosuid,nodev,noexec /dev/mmcblk0p1 "$p"
trap 'umount "$p"' EXIT
sha256sum "$p"/BOOT.bin
'''
            assert run(c,'boot_identity','sh -c '+shlex.quote(check))['output'].split()[0]==FACTORY_SHA
            processes=run(c,'existing_captures',"ps -eo comm,args | grep -E '[w]cis_camera_preview|[w]cis_sdi_reference|[s]dicamera\\+yolov5' || true")
            assert not processes['output'].strip()
            s=c.open_sftp();s.mkdir(release)
            s.put(str(binary),release+'/wcis_camera_preview');s.chmod(release+'/wcis_camera_preview',0o700)
            s.put(str(ROOT/'ps_app/configs/camera-preview.yaml'),release+'/camera-preview.yaml')
            assert run(c,'binary_identity','sha256sum '+release+'/wcis_camera_preview')['output'].split()[0]==sha
            assert run(c,'config_only',release+'/wcis_camera_preview '+release+'/camera-preview.yaml 192.168.1.106')['exit_code']==0
            gate=dict(schema_version=1,boot_id=identity['boot_id'],boot_sha256=FACTORY_SHA,
                      expires_monotonic_us=identity['monotonic_us']+240000000,sdk_probe_permitted=True,capture_permitted=False)
            invalids={'wrong_boot':dict(gate,boot_id='00000000-0000-0000-0000-000000000000'),
                      'wrong_image':dict(gate,boot_sha256='6e81a17a9fb429607b619c653598d4c260c9d820b835e583d8e87bfb6532cb85'),
                      'expired':dict(gate,expires_monotonic_us=1),
                      'capture_not_permitted':gate}
            for name,value in invalids.items():
                path=release+'/'+name+'.json'
                with s.open(path,'w') as f:f.write(json.dumps(value))
                mode='--run-camera' if name=='capture_not_permitted' else '--probe-sdk'
                reply=run(c,'gate_'+name,release+'/wcis_camera_preview '+release+'/camera-preview.yaml 192.168.1.106 '+mode+' --attestation '+path)
                assert reply['exit_code']==2 and 'Hardware entry blocked' in reply['output'] and 'stage=device_open_begin' not in reply['output']
            with s.open(release+'/probe-attestation.json','w') as f:f.write(json.dumps(gate))
            s.close()
            report['deployed']=True;save()
            if not args.run_probe:return
            report['hardware_probe_attempted']=True;save()
            probe=run(c,'probe','timeout --signal=TERM --kill-after=2s 12s '+release+'/wcis_camera_preview '+release+'/camera-preview.yaml 192.168.1.106 --probe-sdk --attestation '+release+'/probe-attestation.json',timeout=18)
            (out/'sdk-probe.log').write_text(probe['output'],encoding='utf-8')
            assert probe['exit_code']==0
            # stdout/stderr can interleave at the SSH channel boundary. Extract
            # the standalone JSON marker without relying on the line prefix.
            lines=re.findall(r'SDK_PROBE (\{[^\r\n]*\})',probe['output'])
            assert len(lines)==1
            evidence=json.loads(lines[0]);assert evidence['version']==0x20230218 and not evidence['camera_configured']
            report['bridge_verified']=True;report['probe_evidence']=evidence
            health=run(c,'after_probe','cat /proc/sys/kernel/random/boot_id; uptime; tail -n 3 /var/log/wcis-heartbeat/heartbeat.log')
            assert identity['boot_id'] in health['output']
            report['board_healthy_after_probe']=True
    except Exception as error:
        report['error_type']=type(error).__name__;raise
    finally:save()


if __name__=='__main__':main()
