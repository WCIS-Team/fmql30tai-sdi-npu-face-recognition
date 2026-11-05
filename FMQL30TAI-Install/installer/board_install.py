"""Board stages. Python 3.8+, stdlib only; no partitioning or formatting."""
import argparse
import contextlib
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import platform
import re
import shutil
import subprocess
import sys
import time
import urllib.request

UNITS = ['wcis-face-recording.service', 'wcis-sdi-vpu-view.service',
         'wcis-face-photo.service', 'wcis-face-storage.service']
BOOT_FILES = ['BOOT.bin', 'Image', 'fmqlmp-verify.dtb', 'uEnv.txt']
BASE = Path('/root/wcis-face')


def run(*args, check=True, timeout=120):
    p = subprocess.run(args, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                       universal_newlines=True, timeout=timeout)
    if check and p.returncode:
        raise RuntimeError('{} failed ({}): {}'.format(args[0], p.returncode, p.stderr[-1500:]))
    return p.stdout.strip()


def sha(path):
    h = hashlib.sha256()
    with open(path, 'rb') as f:
        for part in iter(lambda: f.read(1024*1024), b''): h.update(part)
    return h.hexdigest()


def write_json(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name(path.name + '.new')
    temp.write_text(json.dumps(value, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
    os.replace(str(temp), str(path))


def require_board():
    if os.geteuid() != 0 or platform.machine() != 'aarch64':
        raise RuntimeError('Requires root on the FMQL AArch64 board')
    model = Path('/proc/device-tree/model').read_bytes().decode(errors='replace').strip('\x00')
    if 'FMQL' not in model.upper(): raise RuntimeError('Unexpected board model: '+model)
    return model


def block_inventory():
    result = []
    for p in sorted(Path('/sys/class/block').glob('mmcblk*p*')):
        if not re.fullmatch('mmcblk[0-9]+p[0-9]+', p.name): continue
        device = '/dev/'+p.name
        parent = p.resolve().parent
        kind = (parent/'device/type').read_text().strip()
        values = dict(line.split('=', 1) for line in run('blkid', '-p', '-o', 'export', device, check=False).splitlines() if '=' in line)
        result.append(dict(device=device, media=kind, fstype=values.get('TYPE'), uuid=values.get('UUID')))
    return result


def select_devices(items, require_data=True):
    sd = [i for i in items if i['media'] == 'SD' and i['fstype'] == 'vfat']
    data = [i for i in items if i['media'] == 'MMC' and i['fstype'] == 'ext4']
    if len(sd) != 1: raise RuntimeError('Cannot uniquely identify SD FAT boot partition')
    if len(data) > 1 or (require_data and len(data) != 1):
        raise RuntimeError('Need exactly one existing ext4 eMMC partition; no automatic formatting')
    if data and not re.fullmatch('[0-9a-fA-F-]{36}', data[0]['uuid'] or ''):
        raise RuntimeError('Invalid eMMC UUID')
    return sd[0], (data[0] if data else None)


def copy_missing(source, destination):
    """Initialize absent gallery files without replacing existing user data."""
    if destination.is_symlink(): raise RuntimeError('Data directory is a symbolic link')
    for p in source.rglob('*'):
        target = destination/p.relative_to(source)
        if target.is_symlink(): raise RuntimeError('Unexpected symbolic link in data directory')
        if p.is_dir(): target.mkdir(parents=True, exist_ok=True)
        elif not target.exists(): shutil.copy2(str(p), str(target))


def replace_boot_files(desired, mount, backup, expected):
    """File-level transaction with verification and rollback on I/O errors."""
    existed = {}
    for n in BOOT_FILES:
        existed[n] = (mount/n).exists()
        if existed[n]: shutil.copy2(str(mount/n), str(backup/n))
    try:
        for n in BOOT_FILES:
            staging = mount/(n+'.wcis-new')
            shutil.copyfile(str(desired/n), str(staging))
            if sha(staging) != expected[n]: raise RuntimeError('BOOT staging checksum mismatch')
        for n in BOOT_FILES: os.replace(str(mount/(n+'.wcis-new')), str(mount/n))
        os.sync()
        if any(sha(mount/n) != expected[n] for n in BOOT_FILES): raise RuntimeError('BOOT readback failed')
    except Exception:
        for n in BOOT_FILES:
            if existed[n]: shutil.copyfile(str(backup/n), str(mount/n))
            elif (mount/n).exists(): (mount/n).unlink()
        os.sync()
        raise
    finally:
        for n in BOOT_FILES:
            staging = mount/(n+'.wcis-new')
            if staging.exists(): staging.unlink()


def inspect():
    model = require_board()
    items = block_inventory()
    sd, data = select_devices(items, require_data=False)
    boot_id = Path('/proc/sys/kernel/random/boot_id').read_text().strip()
    marker = BASE/'hardware-review-required.json'
    blocked = marker.exists() and json.loads(marker.read_text()).get('boot_id') == boot_id
    units = {u: run('systemctl', 'show', u, '-p', 'LoadState', '--value', check=False) for u in UNITS}
    return dict(model=model, boot_id=boot_id, partitions=items, sd=sd, data=data,
                existing_install=BASE.exists() or any(v == 'loaded' for v in units.values()),
                current_boot_quarantined=blocked, free_bytes=shutil.disk_usage('/root').free)


def verify_payload(bundle):
    rows = json.loads((bundle/'payload-hashes.json').read_text())['files']
    for name, expected in rows.items():
        p = (bundle/name).resolve()
        if bundle not in p.parents or not p.is_file() or sha(p) != expected:
            raise RuntimeError('Payload integrity error: '+name)


@contextlib.contextmanager
def boot_mount(device, work, writable=False):
    existing = run('findmnt', '-rn', '-S', device, '-o', 'TARGET', check=False)
    if existing:
        raise RuntimeError('SD boot partition already mounted at '+existing+'; unmount it before installation')
    mount = work/'sd-boot'
    mount.mkdir(exist_ok=True)
    options = ('rw' if writable else 'ro')+',nosuid,nodev,noexec'
    run('mount', '-t', 'vfat', '-o', options, device, str(mount))
    try: yield mount
    finally: run('umount', str(mount))


def stop_owned_services(work):
    backup = work/'backup'
    backup.mkdir(exist_ok=True)
    for u in UNITS:
        active = run('systemctl', 'is-active', u, check=False)
        unit = Path('/etc/systemd/system')/u
        if run('systemctl', 'show', u, '-p', 'LoadState', '--value', check=False) == 'loaded':
            contents = run('systemctl', 'cat', u)
            if '/root/wcis-face/' not in contents:
                raise RuntimeError('Refusing to replace an unfamiliar service: '+u)
            if unit.is_file(): shutil.copy2(str(unit), str(backup/u))
            if active in ('active', 'activating', 'deactivating'):
                run('systemctl', 'stop', u, timeout=100)
            pid = run('systemctl', 'show', u, '-p', 'MainPID', '--value')
            if pid != '0': raise RuntimeError('Service did not stop cleanly: '+u)
    # Fail closed on orphaned owner/encoder processes; never kill broad matches.
    processes = run('ps', '-eo', 'comm=').splitlines()
    if any(p.strip().startswith(('wcis_camera_own', 'wcis_face_')) or p.strip() == 'ffmpeg' for p in processes):
        raise RuntimeError('Camera/model/encoder processes remain; inspect before retrying')


def boot_stage(bundle, work):
    state = inspect()
    if state['current_boot_quarantined']:
        raise RuntimeError('Current boot is quarantined; preserve marker and review hardware before installing')
    desired = bundle/'runtime/reference_release/boot'
    expected = {n: sha(desired/n) for n in BOOT_FILES}
    with boot_mount(state['sd']['device'], work) as mount:
        actual = {n: sha(mount/n) if (mount/n).is_file() else None for n in BOOT_FILES}
    if actual == expected:
        return dict(reboot_required=False, boot_id=state['boot_id'], boot_files=expected)
    stop_owned_services(work)
    backup = work/'backup/boot'
    backup.mkdir(parents=True, exist_ok=False)
    with boot_mount(state['sd']['device'], work, writable=True) as mount:
        replace_boot_files(desired, mount, backup, expected)
    # The documented vendor autoload marker is reversible and prevents SDK contention.
    Path('/root/live.disabled').touch()
    if Path('/download.bit').exists():
        shutil.move('/download.bit', str(work/'backup/download.bit'))
    write_json(work/'boot-change.json', dict(before=actual, after=expected, boot_id=state['boot_id']))
    return dict(reboot_required=True, boot_id=state['boot_id'], boot_files=expected,
                backup=str(backup))


def api(path, port=8091):
    with urllib.request.urlopen('http://127.0.0.1:{}{}'.format(port, path), timeout=5) as r:
        return json.load(r)


def verify_services():
    deadline = time.monotonic()+150
    first = None
    while time.monotonic() < deadline:
        try:
            h = api('/api/health'); c = api('/api/camera/status')
            good = h.get('status') == 'ready' and h.get('model_cache_ready') is True and h.get('hardware_admission_ready') is True and c.get('ready') is True
            if good and first and c.get('session') == first.get('session') and c.get('frame_id', 0) > first.get('frame_id', 0):
                return dict(health=h, camera_before=first, camera_after=c)
            first = c if good else None
        except (OSError, ValueError): first = None
        time.sleep(3)
    raise RuntimeError('Services did not reach ready with an advancing camera frame; no automatic hardware retry')


def install_stage(bundle, work):
    state = inspect()
    if state['current_boot_quarantined']: raise RuntimeError('Current boot hardware quarantine; marker retained')
    sd, data = select_devices(state['partitions'])
    if state['free_bytes'] < 500*1024*1024: raise RuntimeError('Insufficient free rootfs space')
    rt = bundle/'runtime'
    stop_owned_services(work)
    if Path('/download.bit').exists():
        raise RuntimeError('Conflicting /download.bit exists; review vendor FPGA autoload before proceeding')
    # Package managers keep their own locking; do not stop unrelated upgrades.
    env = dict(os.environ, DEBIAN_FRONTEND='noninteractive')
    subprocess.run(['apt-get', '-o', 'DPkg::Lock::Timeout=180', 'update'], env=env, check=True, timeout=900)
    packages = ['python3', 'python3-numpy', 'python3-opencv', 'ffmpeg', 'curl', 'util-linux', 'e2fsprogs', 'procps']
    debs = [str(p) for p in sorted((rt/'board/sdk').glob('*.deb'))]
    if len(debs) != 3: raise RuntimeError('Three SDK deb packages required')
    subprocess.run(['apt-get', '-o', 'DPkg::Lock::Timeout=180', 'install', '-y']+packages+debs,
                   env=env, check=True, timeout=1800)
    run('ldconfig')
    for binary in list((rt/'reference_release/app').glob('wcis_*')) + [rt/'reference_release/identity/wcis_face_npu', rt/'reference_release/pad/wcis_face_pad']:
        binary.chmod(0o755)
        p = subprocess.run(['ldd', str(binary)], stdout=subprocess.PIPE, stderr=subprocess.PIPE, universal_newlines=True)
        if p.returncode or 'not found' in p.stdout+p.stderr: raise RuntimeError('Missing runtime library for '+binary.name)
    config = dict(sd_device=sd['device'], data_device=data['device'], data_uuid=data['uuid'], data_mount='/mnt/wcis-data')
    spec = importlib.util.spec_from_file_location('render_install', str(rt/'board/render_install.py'))
    mod = importlib.util.module_from_spec(spec); spec.loader.exec_module(mod)
    rendered = work/'install-tree'
    if rendered.exists(): raise RuntimeError('Install attempt already staged; start a new attempt')
    tree = mod.render(config, rendered)
    # Back up only the application tree; personnel/recording data live on eMMC.
    if BASE.exists():
        run('tar', '-czf', str(work/'backup/application.tar.gz'), '-C', '/root', 'wcis-face', timeout=300)
    Path('/root/live.disabled').touch()
    shutil.copytree(str(tree/'root/wcis-face'), str(BASE), dirs_exist_ok=True)
    Path('/root/wcis-camera-preview').mkdir(exist_ok=True)
    for p in (tree/'etc/systemd/system').glob('*.service'):
        shutil.copy2(str(p), '/etc/systemd/system/'+p.name)
    run('systemctl', 'daemon-reload')
    run('systemctl', 'start', 'wcis-face-storage.service')
    data_root = Path(config['data_mount'])/'wcis-face'
    initial = rendered/'data/wcis-face'
    # Never replace an existing gallery or recording. Add only missing directories/files.
    copy_missing(initial, data_root)
    run('systemctl', 'reset-failed', *UNITS, check=False)
    run('systemctl', 'start', 'wcis-face-photo.service')
    result = verify_services()
    run('systemctl', 'start', 'wcis-sdi-vpu-view.service', 'wcis-face-recording.service')
    for port in (8091, 8092, 8093):
        with urllib.request.urlopen('http://127.0.0.1:{}/'.format(port), timeout=8) as response:
            if response.status != 200: raise RuntimeError('Web page unavailable')
    result['recording'] = api('/api/status', 8093)
    run('systemctl', 'enable', 'wcis-face-photo.service', 'wcis-sdi-vpu-view.service', 'wcis-face-recording.service')
    result['configuration'] = config
    result['scope'] = 'service readiness and advancing camera frames; human face/record/playback acceptance still required'
    write_json(work/'acceptance.json', result)
    return result


def main():
    p = argparse.ArgumentParser()
    p.add_argument('stage', choices=['inspect', 'boot', 'install'])
    p.add_argument('--bundle', type=Path)
    a = p.parse_args()
    if a.stage == 'inspect': result = inspect()
    else:
        bundle = a.bundle.resolve()
        work = bundle.parent
        if not re.fullmatch('/root/wcis-install-runs/[A-Za-z0-9_-]+/payload', str(bundle)):
            raise RuntimeError('Unexpected installation workspace')
        require_board(); verify_payload(bundle)
        result = boot_stage(bundle, work) if a.stage == 'boot' else install_stage(bundle, work)
    print('WCIS_RESULT '+json.dumps(result, ensure_ascii=False), flush=True)


if __name__ == '__main__':
    try: main()
    except Exception as e:
        print('WCIS_ERROR '+str(e), file=sys.stderr, flush=True)
        sys.exit(1)
