"""Explicit, non-destructive schema-1 -> eMMC feature-store migration.

Run while enrollment is stopped. Keeps the source gallery unchanged and requires
the exact bytes of one original per person; never relabels a PNG preview as raw.
"""
import argparse
import copy
import hashlib
import imghdr
import json
import os
from pathlib import Path
import shutil
import subprocess
import uuid

from gallery import Gallery
from persistent_gallery import PersistentGallery, save_durable, sync_directory
from run_photos import sha


def migrate(root, storage_root, mount, expected_uuid):
    root, mount = Path(root), Path(mount).resolve(strict=True)
    info = json.loads(subprocess.run(
        ['findmnt', '-J', '-T', str(mount), '-o', 'TARGET,UUID,FSTYPE'],
        check=True, capture_output=True, text=True).stdout)['filesystems'][0]
    if (not mount.is_mount() or info['target'] != str(mount)
            or info['uuid'] != expected_uuid or info['fstype'] != 'ext4'):
        raise RuntimeError('Migration destination is not the expected eMMC filesystem')
    storage_root = Path(storage_root)
    storage_root.resolve().relative_to(mount)
    legacy = Gallery(root)
    original_db_bytes = legacy.path.read_bytes()
    original_db = json.loads(original_db_bytes)
    if original_db.get('schema_version') != 1:
        raise RuntimeError('Only legacy schema 1 can be migrated')
    expected_templates = legacy.templates()
    required = {p['photos'][0]['sha256'] for p in original_db['people']}
    sources = {}
    for source in list((root / 'samples').glob('*')) + list((root.parents[1] / 'runtime').glob('*/input')):
        if source.is_file():
            digest = sha(source)
            if digest in required and digest not in sources:
                sources[digest] = source
            if sources.keys() == required:
                break
    if sources.keys() != required:
        raise RuntimeError('An original enrollment file is missing; legacy gallery was not changed')
    fingerprint = sha(root / 'models.json')[:16]
    storage_root.mkdir(parents=True, exist_ok=True)
    destination = storage_root / fingerprint
    if destination.exists():
        raise RuntimeError('Migration destination exists; refusing to overwrite')
    pending_root = storage_root / ('.migration-' + uuid.uuid4().hex)
    pending = pending_root / fingerprint
    (pending / 'originals').mkdir(parents=True)
    database = copy.deepcopy(original_db)
    database['schema_version'] = 2
    database['storage_policy'] = 'one_original_per_person'
    try:
        for person in database['people']:
            sample = person['photos'][0]
            data = sources[sample['sha256']].read_bytes()
            if hashlib.sha256(data).hexdigest() != sample['sha256']:
                raise RuntimeError('Original source changed during migration')
            kind = imghdr.what(None, data)
            mime = {'jpeg': 'image/jpeg', 'png': 'image/png', 'webp': 'image/webp',
                    'bmp': 'image/bmp', 'tiff': 'image/tiff'}.get(kind, 'application/octet-stream')
            person['original'] = {'stored_file': person['id'] + '.original',
                'file': sample['file'], 'sha256': sample['sha256'], 'mime': mime,
                'created': sample['created'], 'source_sample_id': sample['id']}
            with (pending / 'originals' / person['original']['stored_file']).open('xb') as stream:
                stream.write(data)
                stream.flush()
                os.fsync(stream.fileno())
        sync_directory(pending / 'originals')
        save_durable(pending / 'gallery.json', database)
        candidate = PersistentGallery(root, pending_root, mount, expected_uuid)
        if candidate.templates() != expected_templates:
            raise RuntimeError('Feature centers changed during migration')
        if legacy.path.read_bytes() != original_db_bytes:
            raise RuntimeError('Enrollment changed during migration; retry while stopped')
        os.replace(pending, destination)
        sync_directory(storage_root)
    finally:
        # Only this invocation's isolated staging directory may be removed.
        if pending_root.exists():
            shutil.rmtree(pending_root)
    return {'migrated': True, 'destination': str(destination),
        'people': len(database['people']),
        'feature_samples': sum(len(p['photos']) for p in database['people']),
        'original_images': len(database['people']), 'templates_bit_exact': True,
        'legacy_gallery_unchanged': True, 'reprocessed_enrollment_models': False,
        'legacy_json_sha256': hashlib.sha256(original_db_bytes).hexdigest(),
        'gallery_json_sha256': sha(destination / 'gallery.json')}


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--root', required=True, type=Path)
    parser.add_argument('--store', required=True, type=Path)
    parser.add_argument('--mount', required=True, type=Path)
    parser.add_argument('--uuid', required=True)
    args = parser.parse_args()
    print(json.dumps(migrate(args.root, args.store, args.mount, args.uuid)))
