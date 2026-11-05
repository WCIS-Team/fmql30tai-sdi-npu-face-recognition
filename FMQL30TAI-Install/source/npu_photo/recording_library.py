"""Completed recording catalog, reversible deletion and indexed JPEG playback."""
from bisect import bisect_right
from collections import OrderedDict
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
import json
import math
import os
import re
import shutil
import threading
import time

ID = re.compile(r'rec-[0-9]{8}T[0-9]{6}Z-[0-9a-f]{12}')
SUFFIXES = ('.mjpeg', '.mp4', '.frames.jsonl', '.json', '.compressed.mp4', '.compression.json')
SHANGHAI = timezone(timedelta(hours=8))


def sync_dir(path):
    if hasattr(os, 'O_DIRECTORY'):
        fd = os.open(str(path), os.O_RDONLY | os.O_DIRECTORY)
        try:
            os.fsync(fd)
        finally:
            os.close(fd)


class Library:
    def __init__(self, store, save, clock=time.time):
        self.store, self.save, self.clock = store, save, clock
        self.root = store.root
        self.trash = self.root / '.trash'
        if self.trash.is_symlink():
            raise ValueError('Unexpected trash symlink')
        self.trash.mkdir(exist_ok=True)
        self.lock = threading.RLock()
        self.readers = {}
        self.cache = OrderedDict()
        self.policy_path = self.root / 'retention.json'
        self.policy = dict(enabled=False, days=7, trash_days=7)
        self.cleanup_error = None
        if self.policy_path.exists():
            self.policy = self.validate_policy(json.loads(self.policy_path.read_text()))
        # Resume only operations explicitly committed before a crash.
        for p in self.trash.glob('rec-*.json'):
            if ID.fullmatch(p.stem) and self._marker(p.stem).get('purging'):
                self.purge(p.stem)

    def path(self, key, suffix):
        if not isinstance(key, str) or not ID.fullmatch(key) or suffix not in SUFFIXES:
            raise ValueError('Invalid recording identifier')
        p = self.root / (key + suffix)
        if p.is_symlink():
            raise ValueError('Unexpected recording symlink')
        return p

    def _marker(self, key):
        self.path(key, '.json')
        p = self.trash / (key+'.json')
        if p.is_symlink():
            raise ValueError('Unexpected trash entry')
        return json.loads(p.read_text()) if p.exists() else None

    def _summary(self, key):
        q = json.loads(self.path(key, '.json').read_text())
        if q.get('id') != key or q.get('state') != 'complete':
            raise ValueError('Recording is not complete')
        required=('.mp4' if q.get('format')=='h264_mp4' else '.mjpeg','.frames.jsonl','.json')
        if not all(self.path(key, suffix).is_file() for suffix in required):
            raise ValueError('Recording files are missing')
        return q

    def compression(self, key):
        p = self.path(key, '.compression.json')
        if not p.exists():
            return None
        q = json.loads(p.read_text())
        if q.get('state') == 'complete':
            media = self.path(key, '.compressed.mp4')
            if not media.is_file() or media.stat().st_size != q.get('bytes'):
                return None
        return q

    @staticmethod
    def date_bound(value, end=False):
        if not value:
            return None
        parsed = datetime.strptime(value, '%Y-%m-%d').replace(tzinfo=SHANGHAI)
        if parsed.strftime('%Y-%m-%d') != value:
            raise ValueError('Date must be YYYY-MM-DD')
        return (parsed + timedelta(days=1 if end else 0)).timestamp()

    def listing(self, *, page=1, limit=20, start='', end='', trash=False):
        if type(page) is not int or not 1 <= page <= 100000 or type(limit) is not int or not 1 <= limit <= 50:
            raise ValueError('Invalid page or page size')
        low, high = self.date_bound(start), self.date_bound(end, True)
        if low is not None and high is not None and low >= high:
            raise ValueError('End date precedes start date')
        with self.lock:
            self.store.guard()
            rows, corrupt = [], 0
            for p in self.root.glob('rec-*.json'):
                if not ID.fullmatch(p.stem):
                    continue
                try:
                    marker = self._marker(p.stem)
                    if bool(marker) != trash or marker and marker.get('purging'):
                        continue
                    q = self._summary(p.stem)
                    stamp = float(q['first']['received_unix'])
                    if not math.isfinite(stamp):
                        raise ValueError('Invalid start time')
                    if (low is not None and stamp < low) or (high is not None and stamp >= high):
                        continue
                    try:
                        compression = self.compression(p.stem)
                    except (OSError, ValueError, TypeError):
                        compression = None
                    rows.append(dict(q, compression=compression, deleted_at=marker['deleted_at'] if marker else None))
                except (OSError, ValueError, KeyError, TypeError):
                    corrupt += 1
            rows.sort(key=lambda q: (q['first']['received_unix'], q['id']), reverse=True)
            offset = (page-1)*limit
            return dict(recordings=rows[offset:offset+limit], total=len(rows), page=page,
                        pages=max(1, (len(rows)+limit-1)//limit), limit=limit,
                        invalid_records=corrupt, timezone='Asia/Shanghai')

    def delete(self, key):
        with self.lock:
            self.store.guard()
            self._summary(key)
            if not self._marker(key):
                self.save(self.trash/(key+'.json'), dict(id=key, deleted_at=self.clock(), purging=False))
            return dict(id=key, deleted=True, recoverable=True)

    def storage_usage(self):
        """File-length snapshot, including indexes; filesystem usage is separate."""
        with self.lock:
            self.store.guard()
            groups = {}
            for p in self.root.glob('rec-*'):
                match = re.fullmatch(r'(rec-[0-9]{8}T[0-9]{6}Z-[0-9a-f]{12})(\.(?:mjpeg|mp4|frames\.jsonl|json|compressed\.mp4|compression\.json))(\.(?:part|ready))?', p.name)
                if not match or p.is_symlink() or not p.is_file():
                    continue
                try:
                    groups.setdefault(match[1], []).append((p.stat().st_size, bool(match[3])))
                except FileNotFoundError:
                    continue  # A writer may rename a completed segment here.
            totals = dict(active_bytes=0, trash_bytes=0, unfinished_bytes=0,
                          active_count=0, trash_count=0, unfinished_count=0)
            for key, files in groups.items():
                kind = 'unfinished'
                if not any(part for _,part in files):
                    try:
                        self._summary(key)
                        kind = 'trash' if self._marker(key) else 'active'
                    except (OSError, ValueError, KeyError, TypeError):
                        pass
                totals[kind+'_bytes'] += sum(size for size,_ in files)
                totals[kind+'_count'] += 1
            disk = shutil.disk_usage(self.root)
            compressed_bytes = potential_saving_bytes = compressed_count = 0
            for key in groups:
                try:
                    q = self.compression(key)
                    if q and q.get('state') == 'complete':
                        compressed_bytes += q['bytes']
                        potential_saving_bytes += q['potential_saving_bytes']
                        compressed_count += 1
                except (OSError, ValueError, KeyError, TypeError):
                    pass
            scratch = self.root / '.compression-work'
            scratch_bytes = sum(p.stat().st_size for p in scratch.glob('*') if p.is_file() and not p.is_symlink()) if not scratch.is_symlink() else 0
            totals['unfinished_bytes'] += scratch_bytes
            used = self.store.used
            remaining = max(0, self.store.quota-used)
            return dict(totals, recording_file_bytes=sum(totals[k] for k in ('active_bytes','trash_bytes','unfinished_bytes')),
                        quota_used_bytes=used, quota_bytes=self.store.quota, quota_remaining_bytes=remaining,
                        disk_total_bytes=disk.total, disk_used_bytes=disk.used, disk_free_bytes=disk.free,
                        disk_reserve_bytes=self.store.reserve,
                        compressed_bytes=compressed_bytes, compressed_count=compressed_count,
                        potential_saving_bytes=potential_saving_bytes, originals_retained=True,
                        available_recording_bytes=max(0,min(remaining,disk.free-self.store.reserve)-1024**2),
                        sampled_at=self.clock())

    def restore(self, key):
        with self.lock:
            self.store.guard()
            self._summary(key)
            marker = self._marker(key)
            if marker and marker.get('purging'):
                raise RuntimeError('Permanent deletion is in progress')
            if marker:
                (self.trash/(key+'.json')).unlink()
                sync_dir(self.trash)
            return dict(id=key, deleted=False)

    def purge(self, key):
        with self.lock:
            self.store.guard()
            marker = self._marker(key)
            if marker is None:
                raise ValueError('Move recording to trash before permanent deletion')
            if self.readers.get(key):
                raise RuntimeError('Recording is being read; retry after playback/download')
            marker['purging'] = True
            self.save(self.trash/(key+'.json'), marker)
            # Journal remains until all three files have been durably removed.
            for suffix in SUFFIXES:
                p = self.path(key, suffix)
                if p.exists():
                    size = p.stat().st_size
                    p.unlink()
                    self.store.account(-size)
            sync_dir(self.root)
            (self.trash/(key+'.json')).unlink()
            sync_dir(self.trash)
            self.cache.pop(key, None)
            return dict(id=key, permanently_deleted=True)

    @contextmanager
    def opened(self, key, suffix):
        with self.lock:
            self.store.guard()
            if self._marker(key):
                raise FileNotFoundError('Recording is in trash')
            summary = self._summary(key)
            if suffix == '.compressed.mp4':
                compressed = self.compression(key)
                if not compressed or compressed.get('state') != 'complete':
                    raise FileNotFoundError('No verified compressed copy')
            f = self.path(key, suffix).open('rb')
            self.readers[key] = self.readers.get(key, 0)+1
        try:
            yield f, summary
        finally:
            f.close()
            with self.lock:
                self.readers[key] -= 1
                if not self.readers[key]:
                    del self.readers[key]

    def frame(self, key, at):
        if not math.isfinite(at) or not 0 <= at <= 301:
            raise ValueError('Invalid playback position')
        with self.opened(key, '.mjpeg') as (video, summary):
            with self.lock:
                index_path = self.path(key, '.frames.jsonl')
                stat = index_path.stat()
                signature = (stat.st_size, stat.st_mtime_ns, summary['bytes'])
                cached = self.cache.get(key)
                if cached is None or cached[0] != signature:
                    if stat.st_size > 16*1024**2:
                        raise ValueError('Frame index too large')
                    rows, offset, last = [], 0, -1.
                    with index_path.open('r') as stream:
                        for line in stream:
                            if len(line) > 16384 or len(rows) >= 10000:
                                raise ValueError('Frame index exceeds limits')
                            row = json.loads(line)
                            t = row['captured_at']-summary['first']['captured_at']
                            length = row['length']
                            if (not math.isfinite(t) or t < last or t < 0 or t > 301
                                    or row['offset'] != offset or type(length) is not int or not 4 <= length <= 5*1024**2):
                                raise ValueError('Invalid frame index')
                            rows.append((t, offset, length))
                            offset += length
                            last = t
                    if not rows or len(rows) != summary['frames'] or offset != os.fstat(video.fileno()).st_size:
                        raise ValueError('Index and recording disagree')
                    self.cache[key] = (signature, rows)
                    while len(self.cache) > 2:
                        self.cache.popitem(last=False)
                self.cache.move_to_end(key)
                rows = self.cache[key][1]
                selected = rows[max(0, bisect_right(rows, (at, float('inf'), float('inf')))-1)]
            t, offset, length = selected
            video.seek(offset)
            jpeg = video.read(length)
            if len(jpeg) != length or not jpeg.startswith(b'\xff\xd8') or not jpeg.endswith(b'\xff\xd9'):
                raise ValueError('Invalid JPEG frame')
            return jpeg, t

    @staticmethod
    def validate_policy(q):
        if (not isinstance(q, dict) or set(q) != {'enabled','days','trash_days'}
                or type(q['enabled']) is not bool or type(q['days']) is not int
                or type(q['trash_days']) is not int or not 1 <= q['days'] <= 365
                or not 1 <= q['trash_days'] <= 365):
            raise ValueError('Retention needs enabled, days and trash_days (1..365)')
        return dict(q)

    def set_policy(self, q):
        q = self.validate_policy(q)
        with self.lock:
            self.store.guard()
            self.save(self.policy_path, q)
            self.policy = q
            return dict(q)

    def maintain(self):
        with self.lock:
            if not self.policy['enabled']:
                return
            self.store.guard()
            now = self.clock()
            # Only complete records are eligible; never remove active .part files.
            for p in self.root.glob('rec-*.json'):
                if not ID.fullmatch(p.stem):
                    continue
                marker = self._marker(p.stem)
                if marker and not self.readers.get(p.stem) and (marker.get('purging') or now-marker['deleted_at'] >= self.policy['trash_days']*86400):
                    self.purge(p.stem)
                elif not marker:
                    q = self._summary(p.stem)
                    if now-q['last']['received_unix'] >= self.policy['days']*86400:
                        self.delete(p.stem)
