"""Jump-host connection using the user's encrypted, local credential."""
from contextlib import contextmanager
import ctypes
from ctypes import wintypes
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / '.tools/python'))
import paramiko

class Blob(ctypes.Structure):
    _fields_ = [('size', wintypes.DWORD), ('data', ctypes.POINTER(ctypes.c_ubyte))]

def jump_password():
    path = Path(r'C:\Users\anxianji\.codex\credentials\school-jump.dpapi')
    raw = bytes.fromhex(path.read_text(encoding='ascii').strip())
    buf = (ctypes.c_ubyte * len(raw)).from_buffer_copy(raw)
    source = Blob(len(raw), buf)
    result = Blob()
    if not ctypes.windll.crypt32.CryptUnprotectData(ctypes.byref(source), None, None, None, None, 0, ctypes.byref(result)):
        raise RuntimeError('Windows credential decryption failed')
    try:
        return ctypes.string_at(result.data, result.size).decode('utf-16-le')
    finally:
        ctypes.memset(result.data, 0, result.size)
        ctypes.windll.kernel32.LocalFree(result.data)

@contextmanager
def jump_connection():
    client = paramiko.SSHClient()
    known = ROOT / 'outputs/school_known_hosts'
    if known.exists():
        client.load_host_keys(str(known))
        # Same pinned jump identity, reached through the user-provided campus
        # endpoint. Only public host keys are aliased; no password is stored.
        prior = client.get_host_keys().lookup('192.168.1.102')
        if prior:
            for kind, key in prior.items():
                client.get_host_keys().add('[10.101.54.192]:18222', kind, key)
        client.set_missing_host_key_policy(paramiko.RejectPolicy())
    else:
        # First-connection trust, equivalent to OpenSSH accept-new. Pin the
        # negotiated host key locally for every subsequent connection.
        client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    try:
        client.connect('10.101.54.192', port=18222, username='user', password=jump_password(),
                       look_for_keys=False, allow_agent=False, timeout=20, auth_timeout=25)
        client.save_host_keys(str(known))
        yield client
    finally:
        client.close()

@contextmanager
def school_connection():
    key_path = Path(r'C:\Users\anxianji\.codex\credentials\school-ed25519')
    if not key_path.exists():
        raise RuntimeError('Provided school SSH key file is absent on this computer: ' + str(key_path))
    with jump_connection() as jump:
        channel = jump.get_transport().open_channel('direct-tcpip', ('127.0.0.1', 13401), ('127.0.0.1', 0))
        client = paramiko.SSHClient()
        known = ROOT / 'outputs/school_target_known_hosts'
        if known.exists():
            client.load_host_keys(str(known))
            client.set_missing_host_key_policy(paramiko.RejectPolicy())
        else:
            client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        try:
            key = paramiko.PKey.from_path(str(key_path))
            client.connect('127.0.0.1', port=13401, username='yizhidi', pkey=key,
                           sock=channel, look_for_keys=False, allow_agent=False,
                           timeout=30, banner_timeout=45, auth_timeout=30)
            client.save_host_keys(str(known))
            yield client
        finally:
            if len(client.get_host_keys()):
                client.save_host_keys(str(known))
            client.close()

if __name__ == '__main__':
    with jump_connection() as client:
        results = []
        for name, cmd in [('user', 'whoami'), ('target_config', 'ssh -G school-guest')]:
            _, out, err = client.exec_command(cmd, timeout=20)
            value = out.read().decode(errors='replace')
            if name == 'target_config':
                value = '\n'.join(row for row in value.splitlines() if row.split(' ', 1)[0] in ('hostname', 'user', 'port', 'identityfile', 'proxycommand', 'proxyjump'))
            print(name + ':\n' + value)
            results.append(name + ':\n' + value)
        (ROOT / 'outputs/school_jump_probe.txt').write_text('\n'.join(results), encoding='utf-8')
