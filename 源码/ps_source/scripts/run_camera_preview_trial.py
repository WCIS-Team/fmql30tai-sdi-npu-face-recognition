"""One explicitly authorized finite camera trial. Never resets/restarts the board."""
from ssh_transport import board_connection, ROOT
import json
import shlex
import time

previous = ROOT/'outputs/camera-preview/board-trial.json'
if previous.exists():
    prior = json.loads(previous.read_text())
    if prior.get('hardware_trial_attempted') and prior.get('error_type') == 'TimeoutError':
        raise SystemExit('Previous hardware trial lost board response. Inspect recovery/SDK entry before another trial; no automatic retry.')

outdir = ROOT/'outputs/camera-preview'
deployment = json.loads((outdir/'board-deployment.json').read_text())
assert deployment['deployed']
release = deployment['remote_directory']
assert release.startswith('/root/wcis-camera-preview/releases/') and '..' not in release
report = dict(remote_directory=release, camera_ready_confirmed_by_user=True,
    geometry='1920x1080 progressive; user-described HD-SDI 1080P', hardware_trial_attempted=True,
    camera_frames_verified=False, firmware_replaced=False, models_loaded=False)
started = time.monotonic()
try:
    with board_connection() as client:
        command = 'bash '+shlex.quote(release+'/run-preview.sh')+' 192.168.1.106'
        _, stdout, _ = client.exec_command(command, timeout=50)
        stdout.channel.set_combine_stderr(True); stdout.channel.settimeout(50)
        with (outdir/'board-capture.log').open('w', encoding='utf-8') as log:
            while True:
                chunk = stdout.channel.recv(8192)
                if not chunk:
                    break
                text = chunk.decode(errors='replace'); log.write(text); log.flush(); print(text,end='',flush=True)
        report['exit_code'] = stdout.channel.recv_exit_status()
        report['elapsed_seconds'] = round(time.monotonic()-started,2)
        _, check, errors = client.exec_command("uptime; systemctl is-active wcis-heartbeat.service; tail -n 8 /var/log/wcis-heartbeat/heartbeat.log; ps -eo pid,stat,comm,args | grep '[w]cis_camera_preview' || true",timeout=15)
        check.channel.settimeout(15)
        report['after_trial'] = check.read().decode(errors='replace')+errors.read().decode(errors='replace')
        print('AFTER_TRIAL\n'+report['after_trial'],flush=True)
except Exception as error:
    report['error_type'] = type(error).__name__;report['elapsed_seconds']=round(time.monotonic()-started,2)
    print('TRIAL_RESULT '+type(error).__name__,flush=True)
finally:
    (outdir/'board-trial.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps({key:report.get(key) for key in ('exit_code','elapsed_seconds','error_type')}),flush=True)
