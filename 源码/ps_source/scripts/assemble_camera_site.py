"""Assemble the existing camera page offline. Never connects to a board."""
import argparse
from pathlib import Path

PANEL = '<!-- WCIS_CAMERA_PANEL -->'
VERSION = '{{CAMERA_PANEL_VERSION}}'


def assemble(template, panel, version):
    if template.count(PANEL) != 1 or template.count(VERSION) != 1:
        raise ValueError('Template must contain each substitution marker exactly once')
    if not version or any(c not in 'abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-_' for c in version):
        raise ValueError('Invalid camera script version')
    if panel.count('id="cameraPanel"') != 1:
        raise ValueError('Expected one camera panel')
    return template.replace(PANEL, panel.strip()).replace(VERSION, version)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--template', type=Path, required=True)
    p.add_argument('--panel', type=Path, required=True)
    p.add_argument('--version', required=True)
    p.add_argument('--out', type=Path, required=True)
    args = p.parse_args()
    result = assemble(args.template.read_text(encoding='utf-8'), args.panel.read_text(encoding='utf-8'), args.version)
    # Refuse to overwrite an existing page, including a running site's file.
    with args.out.open('xb') as f:
        f.write(result.encode('utf-8'))


if __name__ == '__main__':
    main()
