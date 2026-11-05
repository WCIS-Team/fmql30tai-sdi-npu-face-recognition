#!/usr/bin/env python3
"""Run one foreground voice task between verified visual stop and recovery.

Linux/systemd 245+, Python standard library only. Never clears hardware faults.
The transient unit owns the task; ExecStopPost owns recovery, even after SIGKILL.
"""
import argparse
from contextlib import contextmanager, ExitStack
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import signal
import subprocess
import sys
import time
import uuid
from urllib.request import ProxyHandler, Request, build_opener

UNITS = ('wcis-face-photo.service', 'wcis-sdi-vpu-view.service', 'wcis-face-recording.service')
SESSION = 'wcis-vision-voice.service'
BASE = Path('/var/lib/wcis-vision-handoff')
SCRIPT = Path('/usr/local/lib/wcis-vision-handoff/vision_handoff.py')
REQUESTS = Path('/run/wcis-vision-handoff/requests')
HOLD = Path('/run/wcis-vision-handoff/hold.json')
TERMINAL = ('restored', 'deferred_shutdown')
BLOCK_START = ('pausing', 'paused', 'voice_running', 'voice_finished', 'blocked')


def digest(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as f:
        for block in iter(lambda: f.read(1048576), b''):
            h.update(block)
    return h.hexdigest()


def read_json(path):
    return json.loads(Path(path).read_text(encoding='utf-8'))


def atomic(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    tmp = path.with_suffix('.pending')
    with tmp.open('w', encoding='utf-8', newline='\n') as f:
        os.chmod(str(tmp), 0o600)
        json.dump(value, f, indent=2)
        f.write('\n'); f.flush(); os.fsync(f.fileno())
    tmp.replace(path)
    fd = os.open(str(path.parent), os.O_RDONLY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


@contextmanager
def exclusive(path):
    import fcntl
    path = Path(path); path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('a') as f:
        try:
            fcntl.flock(f, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise RuntimeError('Another handoff operation is in progress')
        yield


class Store:
    def __init__(self, base=BASE):
        self.base = Path(base)
        self.path = self.base / 'state.json'

    def load(self):
        return read_json(self.path) if self.path.exists() else None

    def save(self, state):
        state['updated_unix'] = time.time()
        atomic(self.path, state)
        atomic(self.base / 'runs' / (state['token'] + '.json'), state)


class System:
    clock = staticmethod(time.monotonic)
    sleep = staticmethod(time.sleep)

    def __init__(self):
        self.opener = build_opener(ProxyHandler({}))

    def run(self, *args, timeout=100, check=True):
        p = subprocess.run(args, capture_output=True, text=True, timeout=timeout)
        if check and p.returncode:
            raise RuntimeError('Command failed: ' + args[0] + ': ' + p.stderr.strip()[-1000:])
        return p.stdout.strip()

    def boot(self):
        return Path('/proc/sys/kernel/random/boot_id').read_text().strip()

    def unit(self, unit):
        return self.run('systemctl', 'show', unit, '-p', 'ActiveState', '--value')

    def unit_hashes(self):
        return {u: hashlib.sha256(self.run('systemctl', 'cat', u).encode()).hexdigest() for u in UNITS}

    def config(self):
        path = Path('/root/wcis-face/video-stream-current.json')
        q = read_json(path)
        app = Path(q['app'])
        if not app.is_absolute() or app.parent != Path('/root/wcis-face/apps'):
            raise RuntimeError('Unexpected active application path')
        seen = set()
        for row in q['files']:
            name = row['file']; rel = PurePosixPath(name)
            if rel.is_absolute() or '\\' in name or any(x in ('', '.', '..') for x in name.split('/')) or name in seen:
                raise RuntimeError('Unsafe active release manifest')
            seen.add(name)
            if digest(app / name) != row['sha256']:
                raise RuntimeError('Active release checksum mismatch: ' + name)
        if not seen:
            raise RuntimeError('Empty active release manifest')
        if q.get('verified_boot_id') != self.boot():
            raise RuntimeError('Active release is not admitted for this boot')
        # boot_prepare legitimately refreshes these two derived admission fields.
        semantic = {k: v for k, v in q.items() if k not in ('verified_boot_id', 'photo_service_sha256')}
        fingerprint = hashlib.sha256(json.dumps(semantic, sort_keys=True).encode()).hexdigest()
        return dict(app=str(app), release=q['release'], config_sha256=fingerprint,
                    live_required='h264_live.py' in seen)

    def safe_boot(self, boot):
        if self.boot() != boot:
            raise RuntimeError('Boot changed; do not reuse an old stop receipt')
        marker = Path('/root/wcis-face/hardware-review-required.json')
        if marker.exists() and read_json(marker).get('boot_id') == boot:
            raise RuntimeError('Current boot requires hardware review; no automatic restart')

    def api(self, port, path, data=None):
        body = None if data is None else json.dumps(data).encode()
        req = Request('http://127.0.0.1:' + str(port) + path, data=body,
                      headers={'Content-Type': 'application/json'})
        with self.opener.open(req, timeout=2) as response:
            raw = response.read(1048577)
        if len(raw) > 1048576:
            raise RuntimeError('Oversized status response')
        return json.loads(raw)

    def process(self, pid):
        try:
            fields = Path('/proc', str(pid), 'stat').read_text().rsplit(')', 1)[1].split()
            return None if fields[0] in ('Z', 'X') else fields[19]
        except FileNotFoundError:
            return None

    def owner(self, camera, config):
        ctl = read_json('/root/wcis-face/candidates/pad-owner-20261026/owner-current.json')
        if any(ctl[k] != camera[k] for k in ('boot_id', 'pid', 'session')):
            raise RuntimeError('Camera owner identity changed')
        processes = {str(camera[k]): self.process(camera[k]) for k in ('pid', 'encoder_pid', 'muxer_pid')}
        if any(v is None for v in processes.values()):
            raise RuntimeError('Expected camera/encoder/muxer is not running')
        return dict(pid=camera['pid'], session=camera['session'], processes=processes,
                    receipt=str(Path(config['app']) / (str(camera['pid']) + '-owner-stop.json')))

    def closed(self, state):
        receipt = read_json(state['owner']['receipt'])
        if (receipt.get('boot_id') != state['boot_id'] or receipt.get('worker_pid') != state['owner']['pid']
                or receipt.get('sdk_closed') is not True or receipt.get('camera_pending') is not False
                or receipt.get('sessions_released') is not True or receipt.get('exit_code') != 0):
            raise RuntimeError('Missing normal SDK close receipt for this owner and boot')
        for pid, start in state['owner']['processes'].items():
            if self.process(int(pid)) == start:
                raise RuntimeError('Old hardware worker is still alive')
        if any(self.unit(u) not in ('inactive', 'failed') for u in UNITS):
            raise RuntimeError('Visual services did not stop')
        return receipt

    def locks_free(self, release):
        import fcntl
        with ExitStack() as stack:
            for path in (Path(release) / 'npu.lock', Path('/root/wcis-camera-preview/camera.lock')):
                f = stack.enter_context(path.open('a'))
                try:
                    fcntl.flock(f, fcntl.LOCK_EX | fcntl.LOCK_NB)
                except BlockingIOError:
                    raise RuntimeError('Another owner holds a hardware lock')

    def cgroup(self):
        for line in Path('/proc/self/cgroup').read_text().splitlines():
            _, controllers, path = line.split(':', 2)
            if controllers == 'name=systemd':
                return '/sys/fs/cgroup/systemd' + path
        for line in Path('/proc/self/cgroup').read_text().splitlines():
            if line.startswith('0::'):
                return '/sys/fs/cgroup' + line[3:]
        raise RuntimeError('Cannot identify the supervised task cgroup')

    def task_gone(self, state):
        root = Path(state['cgroup'])
        # The fixed session path is owned by systemd, never supplied by a client.
        if root.name != SESSION or not str(root).startswith('/sys/fs/cgroup/'):
            raise RuntimeError('Unexpected voice task cgroup')
        live = set()
        if root.exists():
            for path in root.rglob('cgroup.procs'):
                for pid in path.read_text().split():
                    if int(pid) != os.getpid() and self.process(int(pid)) is not None:
                        live.add(int(pid))
        if live:
            raise RuntimeError('Voice task processes remain; visual restart is blocked')

    def stopping(self):
        return self.run('systemctl', 'is-system-running', check=False) == 'stopping'

    def stop(self, unit):
        self.run('systemctl', 'stop', unit, timeout=100)

    def start(self, *units):
        self.run('systemctl', 'start', *units, timeout=100)

    def hold(self, state):
        value = dict(boot_id=state['boot_id'], token=state['token'])
        if HOLD.exists() and read_json(HOLD) != value:
            raise RuntimeError('Another transaction owns the visual start inhibitor')
        atomic(HOLD, value)

    def release_hold(self, state, required=True):
        if not HOLD.exists() and not required:
            return
        if not HOLD.exists() or read_json(HOLD) != dict(boot_id=state['boot_id'], token=state['token']):
            raise RuntimeError('Missing matching visual start inhibitor')
        HOLD.unlink()


class Handoff:
    def __init__(self, system, store):
        self.s = system; self.store = store

    def save(self, q, phase=None):
        if phase:
            q['phase'] = phase
        self.store.save(q)

    def unchanged(self, q):
        self.s.safe_boot(q['boot_id'])
        if self.s.config() != q['config'] or self.s.unit_hashes() != q['unit_hashes']:
            raise RuntimeError('Visual release or service configuration changed during the task')

    def until(self, check, seconds, label):
        deadline = self.s.clock() + seconds; error = 'not ready'
        while self.s.clock() < deadline:
            try:
                value = check()
                if value:
                    return value
            except (OSError, ValueError, KeyError, RuntimeError) as exc:
                error = str(exc)
            self.s.sleep(.25)
        raise RuntimeError(label + ' deadline: ' + error)

    def finish_pause(self, q):
        self.s.hold(q)
        self.unchanged(q)
        if self.s.unit(UNITS[2]) == 'active':
            self.s.api(8093, '/api/mode', {'mode': 'off'})
            def drained():
                r = self.s.api(8093, '/api/status')
                return r['state'] == 'idle' and r['current'] is None and r['queue_bytes'] == 0 and not r['error']
            self.until(drained, 30, 'Recording drain')
        q['timing']['recording_drained_at'] = self.s.clock(); self.save(q)
        for unit in reversed(UNITS):
            self.s.stop(unit)
        self.s.safe_boot(q['boot_id'])
        q['stop_receipt'] = self.s.closed(q)
        self.s.locks_free(q['config']['release'])
        q['close_verified'] = True
        q['timing']['pause_complete_at'] = self.s.clock()
        q['timing']['pause_seconds'] = q['timing']['pause_complete_at'] - q['timing']['pause_started_at']
        self.save(q, 'paused')

    def pause(self, token, program):
        previous = self.store.load()
        boot = self.s.boot()
        if previous and previous['boot_id'] == boot and previous['phase'] not in TERMINAL:
            raise RuntimeError('An unresolved handoff exists; inspect status before another run')
        self.s.safe_boot(boot)
        if any(self.s.unit(u) != 'active' for u in UNITS):
            raise RuntimeError('Start from three healthy active visual services; no blind restart')
        config = self.s.config(); camera = self.s.api(8091, '/api/camera/status')
        health = self.s.api(8091, '/api/health'); rec = self.s.api(8093, '/api/status')
        if (not camera['ready'] or camera['boot_id'] != boot or health['boot_id'] != boot
                or health['status'] != 'ready' or not health['model_cache_ready']
                or not health['hardware_admission_ready'] or not rec['source_ready'] or rec['error']):
            raise RuntimeError('Visual source/model/recorder is not healthy')
        if rec['mode'] not in ('off', 'auto', 'manual'):
            raise RuntimeError('Unknown recording mode')
        q = dict(version=1, token=token, phase='pausing', boot_id=boot, program=Path(program).name,
                 cgroup=self.s.cgroup(), config=config, owner=self.s.owner(camera, config),
                 unit_hashes=self.s.unit_hashes(), original_recording_mode=rec['mode'], close_verified=False,
                 timing=dict(pause_started_at=self.s.clock()))
        self.save(q)
        self.finish_pause(q)
        return q

    def recover(self, token=None):
        q = self.store.load()
        if q is None or (token is not None and token != q['token']):
            return dict(action='no_matching_transaction')
        if q['phase'] in TERMINAL:
            return q
        if q['boot_id'] != self.s.boot():
            raise RuntimeError('Previous-boot transaction is historical; use normal boot admission')
        if q['phase'] == 'blocked':
            raise RuntimeError('Earlier recovery failed: ' + q.get('error', 'inspect the saved receipt'))
        try:
            self.s.task_gone(q)
            if self.s.stopping():
                self.save(q, 'deferred_shutdown')
                return q
            self.unchanged(q)
            if q['phase'] == 'pausing':
                # Supervisor may have died mid-stop, before the voice task started.
                self.finish_pause(q)
            if not q.get('close_verified'):
                raise RuntimeError('Unsafe pause; automatic device reopening is prohibited')
            if q['phase'] != 'restoring':
                self.s.closed(q)
                self.s.locks_free(q['config']['release'])
                q['timing']['restore_started_at'] = self.s.clock()
                self.save(q, 'restoring')
                self.s.release_hold(q)
            else:
                # Recover the crash window between persisting "restoring" and
                # removing the inhibitor; never remove another session's hold.
                self.s.release_hold(q, required=False)
            started = q['timing']['restore_started_at']
            self.s.start(UNITS[0])
            baseline = None
            def picture():
                nonlocal baseline
                self.s.safe_boot(q['boot_id'])
                h = self.s.api(8091, '/api/health'); c = self.s.api(8091, '/api/camera/status')
                if not (h['status'] == 'ready' and h['model_cache_ready'] and h['hardware_admission_ready'] and c['ready']
                        and h['boot_id'] == c['boot_id'] == q['boot_id']):
                    return False
                if not q['timing'].get('models_ready_at'):
                    q['timing']['models_ready_at'] = self.s.clock()
                identity = (c['pid'], c['session'])
                if baseline and identity == baseline[0] and c['frame_id'] > baseline[1] and c['encoded'] > baseline[2]:
                    if q['config']['live_required']:
                        live = self.s.api(8091, '/api/camera/h264/live-status')
                        if not (live['ready'] and live['pid'] == c['pid'] and live['session'] == c['session']):
                            return False
                    return c
                baseline = (identity, c['frame_id'], c['encoded'])
                return False
            camera = self.until(picture, 60, 'Fresh picture/model readiness')
            q['timing']['picture_ready_at'] = self.s.clock(); q['resumed_owner'] = {k: camera[k] for k in ('pid', 'session', 'boot_id')}
            self.save(q)
            self.s.start(*UNITS[1:])
            def ready_recorder():
                self.s.safe_boot(q['boot_id'])
                r = self.s.api(8093, '/api/status')
                viewer = self.s.api(8092, '/api/status')
                return (r['source_ready'] and not r['error'] and viewer['ready']
                        and viewer['session'] == camera['session'] and viewer['pid'] == camera['pid'])
            self.until(ready_recorder, 30, 'Viewer and recording source')
            self.s.api(8093, '/api/mode', {'mode': q['original_recording_mode']})
            restored = self.s.api(8093, '/api/status')
            if restored['mode'] != q['original_recording_mode']:
                raise RuntimeError('Recording mode was not restored')
            self.s.safe_boot(q['boot_id'])
            q['timing']['restore_complete_at'] = self.s.clock()
            q['timing']['restore_seconds'] = q['timing']['restore_complete_at'] - started
            q['timing']['picture_seconds'] = q['timing']['picture_ready_at'] - started
            q['timing']['models_seconds'] = q['timing']['models_ready_at'] - started
            self.save(q, 'restored')
            return q
        except BaseException as exc:
            try:
                self.s.hold(q)
            except Exception as hold_error:
                q['inhibitor_error'] = str(hold_error)
            if q['phase'] == 'restoring':
                cleanup = {}
                for unit in reversed(UNITS):
                    try:
                        self.s.stop(unit); cleanup[unit] = 'stopped'
                    except Exception as stop_error:
                        cleanup[unit] = str(stop_error)
                q['restore_cleanup'] = cleanup
            q['error'] = str(exc); self.save(q, 'blocked')
            raise


def permit(store, boot):
    q = store.load()
    return q is None or q['boot_id'] != boot or q['phase'] not in BLOCK_START


def dispatch(token, detach=False):
    # Actual voice argv stays in a short-lived 0600 request file. This avoids
    # systemd's environment/specifier expansion and keeps argv out of unit logs.
    args = ['systemd-run', '--unit=' + SESSION, '--collect', '--service-type=exec',
            '--description=WCIS supervised voice task and visual recovery',
            '--property=KillMode=control-group', '--property=SendSIGKILL=no',
            '--property=TimeoutStopSec=240', '--property=Restart=no',
            '--property=ExecStopPost=/usr/bin/python3 ' + str(SCRIPT) + ' _recover --token ' + token]
    if not detach:
        args.append('--wait')
    args += ['/usr/bin/python3', str(SCRIPT), '_run', '--token', token]
    return args


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='action', required=True)
    run = sub.add_parser('run'); run.add_argument('--cwd', default=os.getcwd()); run.add_argument('--detach', action='store_true'); run.add_argument('command', nargs=argparse.REMAINDER)
    for action in ('_run', '_recover'):
        p = sub.add_parser(action); p.add_argument('--token', required=True)
    for action in ('status', 'stop', 'recover', 'permit-start'):
        sub.add_parser(action)
    args = parser.parse_args(argv)
    if hasattr(args, 'token') and not re.fullmatch('[0-9a-f]{32}', args.token):
        parser.error('Invalid handoff token')
    if os.geteuid() != 0:
        parser.error('Run on the board as root (or use sudo)')
    store = Store(); system = System(); ctl = Handoff(system, store)
    if args.action == 'permit-start':
        return 0 if permit(store, system.boot()) else 1
    if args.action == 'status':
        print(json.dumps(dict(boot_id=system.boot(),transaction=store.load(),
                             units={u: system.unit(u) for u in UNITS + (SESSION,)}), indent=2))
        return 0
    if args.action == 'stop':
        system.stop(SESSION); return 0
    if args.action == 'run':
        command = args.command[1:] if args.command[:1] == ['--'] else args.command
        if not command:
            parser.error('Provide a foreground voice command after --')
        with exclusive('/run/lock/wcis-vision-dispatch.lock'):
            if system.unit(SESSION) not in ('inactive', 'failed'):
                raise RuntimeError('A voice handoff session is already active')
            if not permit(store, system.boot()):
                raise RuntimeError('An unresolved handoff exists; inspect status')
            executable = shutil.which(command[0])
            if not executable:
                raise ValueError('Voice executable not found')
            cwd = Path(args.cwd).resolve(strict=True)
            if not cwd.is_dir():
                raise ValueError('Voice working directory must be a directory')
            token = uuid.uuid4().hex
            request = REQUESTS / (token + '.json')
            atomic(request, dict(command=[executable]+command[1:], cwd=str(cwd)))
            try:
                code = subprocess.call(dispatch(token, args.detach))
                if code and request.exists():
                    request.unlink()
                return code
            except KeyboardInterrupt:
                system.stop(SESSION); return 130
    if args.action in ('recover', '_recover'):
        if args.action == 'recover' and system.unit(SESSION) not in ('inactive', 'failed'):
            raise RuntimeError('Session still active; use stop to end the supervised voice task')
        with exclusive('/run/lock/wcis-vision-state.lock'):
            result = ctl.recover(getattr(args, 'token', None))
            request = REQUESTS / (getattr(args, 'token', '') + '.json')
            if args.action == '_recover' and request.exists():
                request.unlink()
        print(json.dumps(result, indent=2)); return 0
    if not system.cgroup().endswith('/' + SESSION):
        raise RuntimeError('Internal run must be supervised by the fixed systemd unit')
    request = REQUESTS / (args.token + '.json')
    payload = read_json(request); request.unlink()
    command = payload['command']
    if not command or not all(isinstance(x, str) for x in command) or not Path(command[0]).is_absolute():
        raise ValueError('Invalid supervised command')
    with exclusive('/run/lock/wcis-vision-state.lock'):
        q = ctl.pause(args.token, command[0])
    child = None
    def terminate(signum, frame):
        if child is not None and child.poll() is None:
            child.terminate()
    signal.signal(signal.SIGTERM, terminate)
    signal.signal(signal.SIGINT, terminate)
    q['timing']['voice_started_at'] = system.clock(); ctl.save(q, 'voice_running')
    try:
        child = subprocess.Popen(command, cwd=payload['cwd'])
        code = child.wait()
    finally:
        q['timing']['voice_exit_observed_at'] = system.clock()
        q['voice_exit_code'] = child.returncode if child is not None else None
        ctl.save(q, 'voice_finished')
    return code if 0 <= code <= 255 else 128 - code


if __name__ == '__main__':
    try:
        sys.exit(main())
    except Exception as error:
        print('Handoff blocked: ' + str(error), file=sys.stderr)
        sys.exit(1)
