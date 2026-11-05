"""Deploy isolated release; validate loader/config only. No Device::Open/run-camera."""
from ssh_transport import board_connection, ROOT
from datetime import datetime, timezone
import hashlib
import json
import shlex

OUT = ROOT/'outputs/camera-preview-guarded'
binary = OUT/'wcis_camera_preview'
config = ROOT/'ps_app/configs/camera-preview.yaml'
sha = hashlib.sha256(binary.read_bytes()).hexdigest()
assert sha == json.loads((OUT/'cross-build.json').read_text())['sha256']
release = '/root/wcis-camera-preview/releases/' + datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ') + '-' + sha[:12]
report = dict(remote_directory=release, sha256=sha, deployed=False, hardware_capture_started=False,
              camera_format_confirmed=False, receiver_ipv4='192.168.1.106', firmware_replaced=False)

def execute(client, name, command):
    _, stdout, stderr = client.exec_command(command, timeout=20)
    stdout.channel.settimeout(20)
    value = stdout.read().decode(errors='replace') + stderr.read().decode(errors='replace')
    code = stdout.channel.recv_exit_status()
    report[name] = dict(exit_code=code, output=value)
    print(name+':\n'+value, flush=True)
    return code, value

try:
    with board_connection() as client:
        code, value = execute(client, 'existing_captures', "ps -eo comm,args | grep -E '[w]cis_camera_preview|[w]cis_sdi_reference|[s]dicamera\\+yolov5' || true")
        if value.strip():
            raise RuntimeError('An existing capture process needs review before deployment')
        code, _ = execute(client, 'create_release', 'mkdir -p /root/wcis-camera-preview/releases && mkdir '+shlex.quote(release))
        if code:
            raise RuntimeError('Release creation failed')
        sftp = client.open_sftp()
        target = release+'/wcis_camera_preview'
        sftp.put(str(binary), target); sftp.chmod(target, 0o700)
        sftp.put(str(config), release+'/camera-preview.yaml')
        launcher = '''#!/usr/bin/env bash
set -euo pipefail
task_here="$(cd -- "$(dirname -- "$0")" && pwd -P)"
task_receiver="${1:-192.168.1.106}"
cd "$task_here"
echo 'Hardware capture disabled: current video-only BOOT lacks the SDK AXI/NPU bridge.' >&2
exit 78
'''
        with sftp.open(release+'/run-preview.sh', 'w') as handle:
            handle.write(launcher)
        sftp.chmod(release+'/run-preview.sh', 0o700)
        with sftp.open(release+'/RELEASE.json', 'w') as handle:
            handle.write(json.dumps(dict(sha256=sha,default_geometry='1920x1080; must verify before capture',
                capture_seconds=0,hardware_capture_enabled=False,automatic_sdi_detection=False,models_required=False),indent=2))
        sftp.close()
        code, value = execute(client, 'remote_sha256', 'sha256sum '+shlex.quote(target))
        if code or value.split()[0] != sha:
            raise RuntimeError('Uploaded binary hash mismatch')
        code, value = execute(client, 'dependencies', 'ldd '+shlex.quote(target))
        if code or 'not found' in value:
            raise RuntimeError('Runtime dependencies unresolved')
        code, _ = execute(client, 'help', 'timeout --signal=TERM --kill-after=2s 10s '+shlex.quote(target)+' --help')
        if code:
            raise RuntimeError('Help check failed')
        code, _ = execute(client, 'config_validation', 'timeout --signal=TERM --kill-after=2s 10s '+
            shlex.quote(target)+' '+shlex.quote(release+'/camera-preview.yaml')+' 192.168.1.106')
        if code:
            raise RuntimeError('Config check failed')
        execute(client, 'persist_release', 'sync '+shlex.quote(target)+' '+shlex.quote(release+'/camera-preview.yaml'))
        report['deployed'] = True
except Exception as error:
    report['error_type'] = type(error).__name__
    print('DEPLOY_RESULT', type(error).__name__, flush=True)
finally:
    (OUT/'board-deployment.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps({key: report[key] for key in ('remote_directory','deployed','hardware_capture_started','sha256')}))
raise SystemExit(0 if report['deployed'] else 1)
