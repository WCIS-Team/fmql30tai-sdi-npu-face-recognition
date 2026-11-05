"""Features plus one original per person on a required, verified Linux mount.

The PS owns the filesystem. This does not implement a PL storage controller or
change face inference; it reuses Gallery's feature normalization and comparison.
An explicit migration must create schema 2 before this store can serve requests.
"""
import fcntl
import copy
import hashlib
import imghdr
import json
import os
import re
import subprocess
import uuid
from contextlib import contextmanager
from pathlib import Path

import numpy as np
from gallery import Gallery
from run_photos import sha


def sync_directory(path):
    fd = os.open(str(path), os.O_RDONLY | os.O_DIRECTORY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def save_durable(path, value):
    """Same-directory replace, with file and directory durability barriers."""
    pending = path.with_name('.' + path.name + '.' + uuid.uuid4().hex + '.tmp')
    try:
        with pending.open('x', encoding='utf-8') as stream:
            json.dump(value, stream, ensure_ascii=False, indent=2)
            stream.write('\n')
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(pending, path)
        sync_directory(path.parent)
    finally:
        if pending.exists():
            pending.unlink()


class PersistentGallery(Gallery):
    def __init__(self, root, storage_root, mount, expected_uuid):
        self.root = Path(root)
        self.mount = Path(mount).resolve(strict=True)
        if not self.mount.is_mount() or not expected_uuid:
            raise RuntimeError('Personnel storage is not mounted')
        info = json.loads(subprocess.run(
            ['findmnt', '-J', '-T', str(self.mount), '-o', 'TARGET,UUID,FSTYPE'],
            check=True, capture_output=True, text=True).stdout)['filesystems'][0]
        if (info['target'] != str(self.mount) or info['uuid'] != expected_uuid
                or info['fstype'] != 'ext4'):
            raise RuntimeError('Personnel storage identity mismatch')
        self.device = self.mount.stat().st_dev
        storage_root = Path(storage_root).resolve(strict=True)
        storage_root.relative_to(self.mount)
        config = json.loads((self.root / 'models.json').read_text())
        self.pipeline = 'yunet-mf-' + config['precision'] + '-npu:' + sha(self.root / 'models.json')
        self.base = storage_root / sha(self.root / 'models.json')[:16]
        self.path = self.base / 'gallery.json'
        self._template_signature = None
        self._template_cache = None
        if not self.path.is_file():
            raise RuntimeError('Personnel store needs explicit migration; no automatic reseeding')
        with self.locked() as db:
            self._recover_orphans(db)

    def guard(self):
        if (not self.mount.is_mount() or self.mount.stat().st_dev != self.device
                or self.base.stat().st_dev != self.device):
            raise RuntimeError('Personnel storage is unavailable; no SD fallback')

    @contextmanager
    def file_lock(self):
        self.guard()
        with (self.base / 'gallery.lock').open('a') as lock:
            fcntl.flock(lock, fcntl.LOCK_EX)
            self.guard()
            yield

    def read_database(self):
        db=json.loads(self.path.read_text(encoding='utf-8'))
        if db.get('schema_version')!=2 or db['pipeline_id']!=self.pipeline:
            raise RuntimeError('Personnel store/model version mismatch')
        return db

    @contextmanager
    def locked(self):
        with self.file_lock():
            yield self.read_database()

    def templates(self):
        # Reload after an atomic add/delete, while keeping unchanged feature
        # centers in PS RAM. Recognition does not reread eMMC image/feature data.
        with self.file_lock():
            stat=self.path.stat()
            signature=(stat.st_dev,stat.st_ino,stat.st_size,stat.st_mtime_ns,stat.st_ctime_ns)
            if signature!=self._template_signature:
                self._template_cache=self.templates_from_db(self.read_database())
                self._template_signature=signature
            return copy.deepcopy(self._template_cache)

    def _original_path(self, person):
        if not re.fullmatch('[0-9a-f]{32}', person['id']):
            raise RuntimeError('Invalid person identifier')
        expected = person['id'] + '.original'
        if person['original']['stored_file'] != expected:
            raise RuntimeError('Invalid original image path')
        return self.base / 'originals' / expected

    def _recover_orphans(self, db):
        referenced = {self._original_path(person).name for person in db['people']}
        for person in db['people']:
            image=self._original_path(person)
            if not image.is_file() or sha(image)!=person['original']['sha256']:
                raise RuntimeError('Personnel original image is missing or changed')
        # An interrupted add/delete may leave our own unreferenced image.
        # Never remove files outside the dedicated originals directory.
        for image in (self.base / 'originals').iterdir():
            if re.fullmatch('[0-9a-f]{32}\.original', image.name) and image.name not in referenced:
                image.unlink()
        sync_directory(self.base / 'originals')

    @staticmethod
    def _check_new(db, name, digest):
        name = name.strip()
        if not name or len(name) > 40 or any(ord(c) < 32 for c in name):
            raise ValueError('姓名需为 1～40 个可显示字符')
        for person in db['people']:
            if any(sample['sha256'] == digest for sample in person['photos']):
                raise ValueError('这张照片已经登记，请使用另一张照片')
            if person['name'] == name and len(person['photos']) >= 30:
                raise ValueError('每个人最多登记 30 份特征')
        if len(db['people']) >= 100 and not any(p['name'] == name for p in db['people']):
            raise ValueError('登记人数已达到 100 人')
        return name

    def check_new(self, name, digest):
        with self.locked() as db:
            return self._check_new(db, name, digest)

    def add(self, name, photo, embedding, filename):
        vector = np.asarray(embedding, np.float64)
        if (vector.shape != (512,) or not np.all(np.isfinite(vector))
                or abs(np.linalg.norm(vector) - 1) > 1e-6):
            raise ValueError('登记特征无效')
        data = Path(photo).read_bytes()
        digest = hashlib.sha256(data).hexdigest()
        with self.locked() as db:
            name = self._check_new(db, name, digest)
            person = next((p for p in db['people'] if p['name'] == name), None)
            if person is None:
                person = {'id': uuid.uuid4().hex, 'name': name, 'photos': []}
                kind = imghdr.what(None, data)
                mime = {'jpeg': 'image/jpeg', 'png': 'image/png', 'webp': 'image/webp',
                        'bmp': 'image/bmp', 'tiff': 'image/tiff'}.get(kind, 'application/octet-stream')
                person['original'] = {'stored_file': person['id'] + '.original',
                    'file': filename, 'sha256': digest, 'mime': mime, 'created': self.now()}
                with self._original_path(person).open('xb') as stream:
                    stream.write(data)
                    stream.flush()
                    os.fsync(stream.fileno())
                sync_directory(self.base / 'originals')
                db['people'].append(person)
            person['photos'].append({'id': uuid.uuid4().hex, 'file': filename,
                'sha256': digest, 'embedding': vector.tolist(), 'created': self.now()})
            db['revision'] += 1
            save_durable(self.path, db)
        return self.public()

    def public(self):
        with self.locked() as db:
            return {'revision': db['revision'], 'storage_policy': 'one_original_per_person',
                'deletion_policy': 'remove_active_data',
                'people': [{'id': p['id'], 'name': p['name'], 'count': len(p['photos']),
                    'photos': [{'id': v['id'], 'file': v['file'], 'created': v['created'],
                        'image': '/gallery-media/' + v['id'] if i == 0 else None,
                        'representative': i == 0}
                        for i, v in enumerate(p['photos'])]} for p in db['people']]}

    def media(self, photo_id):
        with self.locked() as db:
            for person in db['people']:
                if any(sample['id'] == photo_id for sample in person['photos']):
                    return self._original_path(person).read_bytes(), person['original']['mime']
        raise KeyError('登记特征不存在')

    def delete(self, person_id, photo_id=None):
        with self.locked() as db:
            person = next((p for p in db['people'] if p['id'] == person_id), None)
            if person is None:
                raise KeyError('人员不存在')
            removed = [v for v in person['photos'] if photo_id is None or v['id'] == photo_id]
            if not removed:
                raise KeyError('登记特征不存在')
            person['photos'] = [v for v in person['photos'] if v not in removed]
            last = not person['photos']
            if last:
                db['people'].remove(person)
            db['revision'] += 1
            save_durable(self.path, db)
            if last:
                self._original_path(person).unlink()
                sync_directory(self.base / 'originals')
        return self.public()
