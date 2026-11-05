"""Mount the identified personnel eMMC on vendor images without udev.

Never partitions or formats media. Refuses any UUID/type mismatch and never
falls back to SD. A separate service runs this before the model backend.
"""
import argparse
import json
import os
from pathlib import Path
import re
import stat
import subprocess
import time


def command(*args):
    return subprocess.run(args, check=True, capture_output=True, text=True).stdout


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--device', type=Path, required=True)
    parser.add_argument('--mount', type=Path, required=True)
    parser.add_argument('--uuid', required=True)
    parser.add_argument('--unmount', action='store_true')
    args = parser.parse_args()
    if not re.fullmatch('/dev/mmcblk[0-9]+p[0-9]+', str(args.device)):
        raise RuntimeError('Expected a dedicated MMC data partition')
    if not args.mount.is_absolute() or str(args.mount) == '/' or args.mount.is_symlink():
        raise RuntimeError('Invalid personnel mount directory')
    if args.unmount and not args.mount.is_mount():
        return
    deadline = time.monotonic() + 30
    while not args.device.exists() and time.monotonic() < deadline:
        time.sleep(.25)
    if not stat.S_ISBLK(args.device.stat().st_mode):
        raise RuntimeError('Personnel device is not a block device')
    parent = (Path('/sys/class/block') / args.device.name).resolve(strict=True).parent
    if (parent / 'device/type').read_text().strip() != 'MMC':
        raise RuntimeError('Personnel partition is not on eMMC')
    values = dict(line.split('=', 1) for line in command(
        'blkid', '-p', '-o', 'export', str(args.device)).splitlines() if '=' in line)
    if values.get('UUID') != args.uuid or values.get('TYPE') != 'ext4':
        raise RuntimeError('Personnel filesystem UUID/type mismatch')
    if args.mount.is_mount():
        info = json.loads(command('findmnt', '-J', '-T', str(args.mount),
                                  '-o', 'TARGET,UUID,FSTYPE'))['filesystems'][0]
        if info['uuid'] != args.uuid or info['target'] != str(args.mount):
            raise RuntimeError('Another filesystem occupies the personnel mount')
        if args.unmount:
            command('umount', str(args.mount))
        return
    args.mount.mkdir(parents=True, exist_ok=True)
    if any(args.mount.iterdir()):
        raise RuntimeError('Refusing to hide existing files behind a mount')
    check = subprocess.run(['e2fsck', '-p', str(args.device)], capture_output=True, text=True)
    if check.returncode not in (0, 1):
        raise RuntimeError('Personnel filesystem needs manual repair')
    command('mount', '-t', 'ext4', '-o',
            'rw,nosuid,nodev,noexec,noatime,errors=remount-ro',
            str(args.device), str(args.mount))
    info = json.loads(command('findmnt', '-J', '-T', str(args.mount),
                              '-o', 'TARGET,UUID,FSTYPE'))['filesystems'][0]
    if info['uuid'] != args.uuid or info['target'] != str(args.mount):
        raise RuntimeError('Mounted personnel filesystem identity did not match')
    print('Personnel eMMC filesystem mounted and verified', flush=True)


if __name__ == '__main__':
    main()
