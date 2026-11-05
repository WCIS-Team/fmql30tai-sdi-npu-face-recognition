"""Board launcher for the independently validated ModelBackend DDR replay.

Temporarily yields the photo service's device ownership to a bounded replay,
then restores the service. This is test setup, not a live camera scheduler.
"""
import argparse
import fcntl
import hashlib
import json
import signal
import subprocess
import sys
import time
import urllib.request
import uuid
from pathlib import Path


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--frames',type=int,default=30)
    parser.add_argument('--period-ms',type=int,default=0)
    parser.add_argument('--seed',choices=('face-bgrx','face-rgb565','no-face','two-faces'),default='face-bgrx')
    parser.add_argument('--stream',action='store_true',help='Binary SSH video input; requires an exec channel without PTY')
    parser.add_argument('--config',type=Path)
    args=parser.parse_args()
    if not 1<=args.frames<=300 or not 0<=args.period_ms<=5000:
        parser.error('Use 1..300 iterations and a period of 0..5000 ms')
    config_path=args.config or Path('/root/wcis-face/video-stream-current.json' if args.stream else '/root/wcis-face/replay-current.json')
    cfg=json.loads(config_path.read_text())
    app,root=Path(cfg['app']),Path(cfg['release'])
    boot=Path('/proc/sys/kernel/random/boot_id').read_text().strip()
    if boot!=cfg['verified_boot_id']:
        raise RuntimeError('Board boot changed; revalidate the deployed backend before replay')
    marker=root.parents[1]/'hardware-review-required.json'
    if marker.exists() and json.loads(marker.read_text()).get('boot_id')==boot:
        raise RuntimeError('Current boot requires hardware review')
    for record in cfg['files']:
        if hashlib.sha256((app/record['file']).read_bytes()).hexdigest()!=record['sha256']:
            raise RuntimeError('Replay artifact checksum mismatch')
    evidence=json.loads(Path(cfg['verification']).read_text())
    if not evidence['passed'] or evidence['app']!=str(app):
        raise RuntimeError('Replay backend has no matching successful validation')
    unit=Path('/etc/systemd/system/wcis-face-photo.service').read_bytes()
    if hashlib.sha256(unit).hexdigest()!=cfg['photo_service_sha256']:
        raise RuntimeError('Photo service changed; refresh the replay handoff configuration')
    was_active=subprocess.run(['systemctl','is-active','--quiet','wcis-face-photo.service']).returncode==0
    paused=False;child=None;stop_requested=False
    def stop(signum,frame):
        nonlocal stop_requested
        stop_requested=True
        if child is not None and child.poll() is None:child.send_signal(signal.SIGTERM)
    signals={sig:signal.signal(sig,stop) for sig in (signal.SIGTERM,signal.SIGINT,signal.SIGHUP)}
    try:
        with (root/'npu.lock').open('a') as lock:
            fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
            if was_active:
                subprocess.run(['systemctl','stop','wcis-face-photo.service'],check=True,timeout=75)
                paused=True
        if stop_requested:return 0
        out=root.parents[1]/'runtime'/(('video-stream-' if args.stream else 'frame-replay-')+uuid.uuid4().hex)
        fs=cfg['filesystem']
        if args.stream:
            command=[sys.executable,'-u',str(app/'receive_video_stream.py'),'--root',str(root),
                     '--out',str(out),'--max-frames',str(args.frames),
                     '--gallery-store',fs['mount']+'/wcis-face/galleries',
                     '--gallery-mount',fs['mount'],'--gallery-uuid',fs['uuid']]
            print(json.dumps(dict(event='launch',out=str(out))),flush=True)
        else:
            command=[sys.executable,'-u',str(app/'run_frame_replay.py'),'--root',str(root),
                     '--seed',str(Path(cfg['seeds_dir'])/(args.seed+'.json')),'--out',str(out),
                     '--frames',str(args.frames),'--period-ms',str(args.period_ms),
                     '--gallery-store',fs['mount']+'/wcis-face/galleries',
                     '--gallery-mount',fs['mount'],'--gallery-uuid',fs['uuid']]
            print('REPLAY_OUTPUT '+str(out),flush=True)
        # A terminal Ctrl+C must reach this launcher only. SDK workers inherit
        # the child's separate session; forward SIGTERM to Python's PID rather
        # than sending an interrupt to a process group containing active DMA.
        child=subprocess.Popen(command,start_new_session=True)
        if stop_requested:child.send_signal(signal.SIGTERM)
        # The child handles SDK deadlines and drains on SIGTERM. Never KILL it.
        return child.wait()
    finally:
        try:
            if paused:
                if child is not None and child.poll() is None:
                    print('Replay still owns hardware; photo service remains stopped',file=sys.stderr)
                elif marker.exists() and json.loads(marker.read_text()).get('boot_id')==boot:
                    print('Hardware review required; photo service remains stopped',file=sys.stderr)
                else:
                    subprocess.run(['systemctl','start','wcis-face-photo.service'],check=True,timeout=45)
                    opener=urllib.request.build_opener(urllib.request.ProxyHandler({}))
                    for attempt in range(100):
                        try:
                            with opener.open(cfg['photo_health_url'],timeout=2) as r:health=json.loads(r.read())
                            if health.get('status')=='ready':break
                        except OSError:pass
                        time.sleep(.25)
                    else:raise RuntimeError('Photo service did not become ready after replay')
                    if args.stream:print(json.dumps(dict(event='restored',status='ready')),flush=True)
                    else:print('REPLAY_FINISHED photo_service_restored=ready',flush=True)
        finally:
            for sig,handler in signals.items():signal.signal(sig,handler)


if __name__=='__main__':
    raise SystemExit(main())
