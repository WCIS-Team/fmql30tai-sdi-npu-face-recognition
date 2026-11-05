"""Render a fresh-board install tree offline. Never connects to hardware."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import shutil

ROOT = Path(__file__).resolve().parents[1]
APP = '/root/wcis-face/apps/vision-20261103'
REL = '/root/wcis-face/releases/20261014-b5a454c11d22'
PAD = '/root/wcis-face/candidates/pad-20261018-7d22c90e30'
READY = '/root/wcis-face/candidates/face-camera-ready-20261020'
CONTROL = '/root/wcis-face/candidates/pad-owner-20261026/owner-current.json'
# These five binaries are regenerable (README section 2): rebuilding with a
# different toolchain or source path yields a different but equivalent file,
# so a fixed hash cannot pin them. They only get a basic integrity check;
# models, boot files and SDK debs stay hash-pinned.
REGENERABLE_ELFS = {
    'reference_release/app/wcis_camera_owner',
    'reference_release/app/wcis_face_cached',
    'reference_release/app/wcis_face_pl_retained',
    'reference_release/identity/wcis_face_npu',
    'reference_release/pad/wcis_face_pad',
}
ELF_HEAD_FIXED = (b'\x7fELF\x02\x01\x01', b'\x03\x00\xb7\x00')  # (ident[0:7], e_type+e_machine)
def is_aarch64_elf(p):
    head = p.read_bytes()[:20]
    return head[:7] == ELF_HEAD_FIXED[0] and head[16:18] in (b'\x02\x00', b'\x03\x00') and head[18:20] == b'\xb7\x00'

def sha(p): return hashlib.sha256(p.read_bytes()).hexdigest()
def write(root, path, data):
    p = root / path.lstrip('/')
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(data if isinstance(data, str) else json.dumps(data, indent=2)+'\n', encoding='utf-8')

def render(config, output, boot_bin=None):
    for key in ('data_device', 'sd_device'):
        if not re.fullmatch(r'/dev/mmcblk[0-9]+p[0-9]+', config[key]): raise ValueError('Invalid MMC partition')
    if config['data_device'].split('p')[0] == config['sd_device'].split('p')[0]: raise ValueError('SD and data must use different MMC media')
    if not re.fullmatch(r'[0-9a-fA-F-]{36}', config['data_uuid']): raise ValueError('Set the real ext4 data UUID')
    if not re.fullmatch(r'/mnt/[a-zA-Z0-9_-]+', config['data_mount']): raise ValueError('Use a dedicated mount below /mnt')
    if output.exists(): raise FileExistsError('Output already exists; choose a new directory')
    # Verify packaged assets before producing an installation candidate.
    manifest=json.loads((ROOT/'filelist.json').read_text(encoding='utf-8'))
    for row in manifest['files']:
        if not row['path'].startswith(('reference_release/', 'board/')):
            continue
        if row['path'] in REGENERABLE_ELFS:
            p=ROOT/row['path']
            if not p.is_file() or p.stat().st_size < 100000 or not is_aarch64_elf(p):
                raise ValueError('Regenerable ELF missing or not aarch64: '+row['path'])
            continue
        if sha(ROOT/row['path']) != row['sha256']:
            raise ValueError('Package asset checksum mismatch: '+row['path'])
    if boot_bin is not None:
        boot_bin = Path(boot_bin).resolve()
        if not boot_bin.is_file() or boot_bin.stat().st_size < 64:
            raise ValueError('Selected BOOT.bin missing or too short')
    # Keep the original package immutable; stage a matched boot/install pair.
    shutil.copytree(ROOT/'reference_release/boot', output/'boot')
    if boot_bin is not None:
        shutil.copy2(boot_bin, output/'boot/BOOT.bin')
    tree=output/'rootfs' 
    for source, dest in [('app', APP), ('identity', REL), ('pad', PAD), ('recorder','/root/wcis-face/recorder')]:
        shutil.copytree(ROOT/'reference_release'/source, tree/dest.lstrip('/'))
    for p in (tree/APP.lstrip('/')).glob('wcis_*'): p.chmod(0o755)
    (tree/(PAD+'/wcis_face_pad').lstrip('/')).chmod(0o755)
    legacy=tree/(REL+'/wcis_face_npu').lstrip('/')
    if legacy.exists(): legacy.chmod(0o755)
    (tree/(REL+'/samples').lstrip('/')).mkdir(parents=True)
    write(tree, REL+'/samples/sources.json', {'files':[]})
    for name in ['live','sd']:(tree/(READY+'/'+name).lstrip('/')).mkdir(parents=True,exist_ok=True)
    (tree/'root/wcis-camera-preview').mkdir(parents=True)
    (tree/'root/wcis-face/candidates/pad-owner-20261026').mkdir(parents=True)
    write(tree, '/root/live.disabled', 'Vision owns the SDK; disable vendor autorun.\n')
    boot={p.name:sha(p) for p in (output/'boot').iterdir() if p.is_file()}
    write(output, 'boot-input.json', {'boot_files':boot,'rebuilt_boot_selected':boot_bin is not None,'hardware_accepted':False})
    files=[{'file':p.relative_to(ROOT/'reference_release/app').as_posix(),'sha256':sha(p)} for p in (ROOT/'reference_release/app').rglob('*') if p.is_file()]
    write(tree, '/root/wcis-face/video-stream-current.json', {'app':APP,'release':REL,'files':files,'verified_boot_id':None,'verification':{'passed':False,'reason':'Fresh board not yet accepted'}})
    write(tree, READY+'/camera-control.json', {'root':READY+'/live','unit':'wcis-sdi-camera-live.service','boot_sha256':boot['BOOT.bin']})
    write(tree, READY+'/deployment.json', dict(app=APP,boot_files=boot,sd_device=config['sd_device']))
    shutil.copy2(ROOT/'board/boot_prepare.py', tree/(READY+'/boot_prepare.py').lstrip('/'))
    storage='/root/wcis-face/tools/mount_face_store.py'
    (tree/Path(storage.lstrip('/')).parent).mkdir(parents=True,exist_ok=True)
    shutil.copy2(ROOT/'board/mount_face_store.py',tree/storage.lstrip('/'))
    m=config['data_mount'];u=config['data_uuid'];d=config['data_device']
    owner=sha(ROOT/'reference_release/app/wcis_camera_owner')
    def unit(name, body):write(tree,'/etc/systemd/system/'+name,body)
    unit('wcis-face-storage.service', f'''[Unit]
Description=Verified vision data mount
After=local-fs.target
Before=wcis-face-photo.service
[Service]
Type=oneshot
RemainAfterExit=yes
ExecStart=/usr/bin/python3 {storage} --device {d} --mount {m} --uuid {u}
ExecStop=/usr/bin/python3 {storage} --device {d} --mount {m} --uuid {u} --unmount
TimeoutStartSec=90
TimeoutStopSec=30
''')
    unit('wcis-face-photo.service',f'''[Unit]
Description=Vision identity and PAD backend
After=network-online.target wcis-face-storage.service
Requires=wcis-face-storage.service
[Service]
Type=simple
Environment=WCIS_PREVIEW_CODEC=h264 WCIS_PREVIEW_SIZE=540 OPENCV_IO_MAX_IMAGE_PIXELS=16000000 PYTHONDONTWRITEBYTECODE=1
WorkingDirectory={APP}
ExecStartPre=/usr/bin/python3 {READY}/boot_prepare.py
ExecStart=/usr/bin/python3 -u {APP}/serve_photos.py --root {REL} --site {APP}/site --host 0.0.0.0 --port 8091 --pl-executable {APP}/wcis_face_pl_retained --npu-cache-executable {APP}/wcis_face_cached --gallery-store {m}/wcis-face/galleries --gallery-mount {m} --gallery-uuid {u} --camera-owner-executable {APP}/wcis_camera_owner --camera-owner-sha256 {owner} --camera-owner-control {CONTROL} --camera-owner-fps 30 --camera-native-inputs --camera-pad-bundle {PAD}
Restart=no
KillMode=mixed
TimeoutStopSec=75
SendSIGKILL=no
[Install]
WantedBy=multi-user.target
''')
    unit('wcis-sdi-vpu-view.service',f'''[Unit]
Description=Vision preview
After=wcis-face-photo.service
[Service]
ExecStart=/usr/bin/python3 {APP}/vpu_live_server.py --control {CONTROL} --host 0.0.0.0 --port 8092
Restart=no
[Install]
WantedBy=multi-user.target
''')
    unit('wcis-face-recording.service',f'''[Unit]
Description=Vision MP4 recorder
After=wcis-face-photo.service wcis-face-storage.service
Requires=wcis-face-storage.service
[Service]
WorkingDirectory=/root/wcis-face/recorder
ExecStart=/usr/bin/python3 /root/wcis-face/recorder/recording_service.py --control {CONTROL} --storage {m}/wcis-face/recordings --mount {m} --uuid {u} --mode off --segment-seconds 60 --quota-mib 4096 --host 0.0.0.0 --backend http://127.0.0.1:8091
Restart=no
TimeoutStopSec=45
MemoryMax=192M
TasksMax=24
[Install]
WantedBy=multi-user.target
''')
    fingerprint=sha(ROOT/'reference_release/identity/models.json')
    pipeline='yunet-mf-fp16-npu:'+fingerprint
    data=output/'data/wcis-face/galleries'/fingerprint[:16]
    (data/'originals').mkdir(parents=True)
    write(output, str(data.relative_to(output)/'gallery.json'), {'schema_version':2,'pipeline_id':pipeline,'revision':0,'people':[],'storage_policy':'one_original_per_person'})
    (output/'data/wcis-face/recordings').mkdir(parents=True)
    write(output,'board.json',config)
    return tree

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--config',type=Path,required=True);p.add_argument('--out',type=Path,required=True);p.add_argument('--boot-bin',type=Path,help='Explicit rebuilt BOOT.bin; still requires board acceptance');a=p.parse_args()
    print(render(json.loads(a.config.read_text(encoding='utf-8')),a.out.resolve(),a.boot_bin))
