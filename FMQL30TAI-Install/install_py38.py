#!/usr/bin/env python3.8
"""Python 3.8 entry point; imports offline SSH dependencies for this platform."""
import hashlib
import json
import platform
from pathlib import Path
import sys


def check_files(root):
    manifest = json.loads((root/'MANIFEST.json').read_text(encoding='utf-8'))
    for row in manifest['files']:
        p = (root/row['path']).resolve()
        if root not in p.parents or not p.is_file() or p.stat().st_size != row['bytes']:
            raise RuntimeError('安装文件缺失或路径异常：'+row['path'])
        h = hashlib.sha256()
        with p.open('rb') as f:
            for b in iter(lambda: f.read(1024*1024), b''): h.update(b)
        if h.hexdigest() != row['sha256']: raise RuntimeError('安装文件校验失败：'+row['path'])
    return len(manifest['files'])


def main():
    if sys.version_info[:2] != (3, 8) or platform.python_implementation() != 'CPython':
        raise RuntimeError('请使用 CPython 3.8.x：python3.8 install_py38.py；随包离线依赖按 Python 3.8 配套。')
    root = Path(__file__).resolve().parent
    machine = platform.machine().lower()
    tag = {'linux':'linux-x86_64', 'win32':'windows-amd64'}.get(sys.platform)
    if not tag or machine not in ('amd64','x86_64'):
        raise RuntimeError('本机启动支持 Linux x86_64 / Windows AMD64；请在编译电脑运行，不在板卡上运行。')
    # Verify packaged code before importing native dependencies, including --check.
    check_files(root)
    sys.path.insert(0, str(root/'vendor'/tag))
    sys.path.insert(0, str(root/'installer'))
    try:
        import paramiko
        import cryptography
        import nacl
        import bcrypt
    except ImportError as e:
        raise RuntimeError('离线 SSH 组件加载失败，请完整解压并使用 64 位 Python 3.8：'+str(e))
    import install
    install.cli()


if __name__ == '__main__':
    try: main()
    except KeyboardInterrupt: sys.exit(130)
    except Exception as e:
        print('未完成：'+str(e), file=sys.stderr)
        sys.exit(1)
