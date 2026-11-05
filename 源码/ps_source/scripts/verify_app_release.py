"""Verify explicit local release files; no SSH, service changes, or hardware access.

Success proves file integrity against the supplied manifest, not live readiness.
Extra runtime files are ignored; only manifest entries are checked.
"""
import argparse
import hashlib
import json
from pathlib import Path, PurePosixPath
import re


def digest(path):
    h = hashlib.sha256()
    with path.open('rb') as f:
        for block in iter(lambda: f.read(1024 * 1024), b''):
            h.update(block)
    return h.hexdigest()


def verify(root, manifest):
    root = Path(root).resolve(strict=True)
    if not isinstance(manifest, dict):
        raise ValueError('Expected a JSON manifest object')
    entries = manifest.get('files')
    if not isinstance(entries, list) or not entries:
        raise ValueError('Expected a non-empty files list')
    seen = set()
    rows = []
    for item in entries:
        name = item['file']
        expected = item['sha256']
        if not isinstance(name, str) or not name or '\\' in name or ':' in name:
            raise ValueError('Invalid relative file name')
        rel = PurePosixPath(name)
        if rel.is_absolute() or any(x in ('', '.', '..') for x in name.split('/')):
            raise ValueError('Unsafe relative file name: ' + name)
        if name.casefold() in seen:
            raise ValueError('Duplicate file name: ' + name)
        seen.add(name.casefold())
        if not isinstance(expected, str) or not re.fullmatch('[0-9a-f]{64}', expected):
            raise ValueError('Invalid SHA256: ' + name)
        path = root
        for part in rel.parts:
            path = path / part
            if path.is_symlink():
                raise ValueError('Symbolic link is not a release file: ' + name)
        resolved = path.resolve()
        if root not in resolved.parents:
            raise ValueError('File escapes release root: ' + name)
        actual = digest(path) if path.is_file() else None
        rows.append(dict(file=name,expected=expected,actual=actual,match=actual == expected))
    return dict(passed=all(x['match'] for x in rows), checked=len(rows),
                scope='file_integrity_only', live_readiness_verified=False, files=rows)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--root', type=Path, required=True)
    p.add_argument('--manifest', type=Path, required=True)
    p.add_argument('--out', type=Path)
    args = p.parse_args()
    try:
        result = verify(args.root, json.loads(args.manifest.read_text(encoding='utf-8-sig')))
    except (OSError, ValueError, KeyError, TypeError) as error:
        result = dict(passed=False, error=str(error), scope='file_integrity_only', live_readiness_verified=False)
    text = json.dumps(result, ensure_ascii=False, indent=2)
    if args.out:
        with args.out.open('x', encoding='utf-8') as f:
            f.write(text + '\n')
    print(text)
    return 0 if result['passed'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
