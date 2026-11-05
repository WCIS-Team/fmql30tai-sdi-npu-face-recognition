#!/usr/bin/env python3
"""Install/remove the handoff CLI and guarded visual service drop-ins on a board."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import sys
import time

from vision_handoff import BASE, SCRIPT, SESSION, UNITS, HOLD, System, Store, TERMINAL, exclusive

LAUNCHER = Path('/usr/local/sbin/wcis-visionctl')
DROPIN = '20-wcis-vision-handoff.conf'


def guard_bytes():
    # Native unit conditions skip before ExecStart without triggering the
    # viewer's Restart=on-failure loop on this board's systemd 245 build.
    return ('[Unit]\nConditionPathExists=!' + str(HOLD) + '\n').encode()


def write(path, data, mode):
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix('.installing'); tmp.write_bytes(data); tmp.chmod(mode); tmp.replace(path)


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--check', action='store_true')
    p.add_argument('--uninstall', action='store_true')
    args = p.parse_args(argv)
    if os.geteuid() != 0:
        p.error('Run this installer on the board as root (or use sudo)')
    system = System(); source = Path(__file__).with_name('vision_handoff.py')
    if args.check:
        launcher = ('#!/bin/sh\nexec /usr/bin/python3 ' + str(SCRIPT) + ' "$@"\n').encode()
        installed = (SCRIPT.is_file() and SCRIPT.read_bytes() == source.read_bytes()
                     and LAUNCHER.is_file() and LAUNCHER.read_bytes() == launcher)
        conditions = {}
        for u in UNITS:
            path = Path('/etc/systemd/system') / (u + '.d') / DROPIN
            conditions[u] = path.is_file() and path.read_bytes() == guard_bytes()
        print(json.dumps(dict(installed=installed,guards=conditions,units={u: system.unit(u) for u in UNITS})))
        return 0 if installed and all(conditions.values()) else 1
    with exclusive('/run/lock/wcis-vision-dispatch.lock'):
        if system.unit(SESSION) not in ('inactive', 'failed'):
            raise RuntimeError('Do not change installation during a voice session')
        previous = Store().load()
        if previous and previous['boot_id'] == system.boot() and previous['phase'] not in TERMINAL:
            raise RuntimeError('Resolve the pending handoff before changing installation')
        paths = [Path('/etc/systemd/system') / (u + '.d') / DROPIN for u in UNITS]
        if args.uninstall:
            for path in paths:
                expected = guard_bytes()
                if path.exists() and path.read_bytes() != expected:
                    raise RuntimeError('Modified guard; inspect before uninstalling: ' + str(path))
            for path in paths:
                if path.exists():
                    path.unlink()
            expected_launcher = ('#!/bin/sh\nexec /usr/bin/python3 ' + str(SCRIPT) + ' "$@"\n').encode()
            if LAUNCHER.exists() and LAUNCHER.read_bytes() == expected_launcher:
                LAUNCHER.unlink()
            system.run('systemctl', 'daemon-reload')
            print('Guards and launcher removed. Library, receipts and enabled states retained for review.')
            return 0
        for unit in UNITS:
            if system.run('systemctl', 'show', unit, '-p', 'LoadState', '--value') != 'loaded':
                raise RuntimeError('Missing visual service: ' + unit)
        compile(source.read_bytes(), str(source), 'exec')
        system.config()
        data = source.read_bytes()
        launcher = ('#!/bin/sh\nexec /usr/bin/python3 ' + str(SCRIPT) + ' "$@"\n').encode()
        guard = guard_bytes()
        for path in paths:
            if path.exists() and path.read_bytes() != guard:
                raise RuntimeError('Existing custom handoff guard; refusing to overwrite it')
        # Installing adds conditions only; the running visual owner is not restarted.
        write(SCRIPT, data, 0o755); write(LAUNCHER, launcher, 0o755)
        for path in paths:
            write(path, guard, 0o644)
        system.run('systemctl', 'daemon-reload')
        enabled_before = {u: system.run('systemctl', 'is-enabled', u, check=False) for u in UNITS}
        system.run('systemctl', 'enable', *UNITS)
        receipt = dict(installed_unix=time.time(),source_sha256=hashlib.sha256(data).hexdigest(),
                       enabled_before=enabled_before,enabled_after={u: system.run('systemctl', 'is-enabled', u, check=False) for u in UNITS},
                       active={u: system.unit(u) for u in UNITS},owner_restarted_by_installer=False)
        BASE.mkdir(parents=True, exist_ok=True, mode=0o700)
        (BASE/'installation.json').write_text(json.dumps(receipt, indent=2)+'\n')
        print(json.dumps(receipt, indent=2))
    return 0


if __name__ == '__main__':
    try:
        sys.exit(main())
    except Exception as error:
        print('Installation blocked: ' + str(error), file=sys.stderr)
        sys.exit(1)
