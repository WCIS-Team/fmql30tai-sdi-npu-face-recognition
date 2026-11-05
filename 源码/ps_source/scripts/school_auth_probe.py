"""Read the SSH handshake and permitted methods; no credential guessing."""
from school_connection import jump_connection, paramiko, ROOT
import hashlib
import base64
import json

with jump_connection() as jump:
    channel = jump.get_transport().open_channel('direct-tcpip', ('127.0.0.1', 13401), ('127.0.0.1', 0))
    transport = paramiko.Transport(channel)
    try:
        transport.start_client(timeout=15)
        key = transport.get_remote_server_key()
        known = paramiko.HostKeys(str(ROOT / 'outputs/school_target_known_hosts'))
        assert known.check('[127.0.0.1]:13401', key), 'Target host key changed'
        result = {'server_version':transport.remote_version,
                  'host_fingerprint':'SHA256:' + base64.b64encode(hashlib.sha256(key.asbytes()).digest()).decode().rstrip('=')}
        try:
            transport.auth_none('YiZhidi')
            result['none_auth'] = 'accepted'
        except paramiko.BadAuthenticationType as ex:
            result['allowed_authentication'] = ex.allowed_types
        (ROOT / 'outputs/school_auth_probe.json').write_text(json.dumps(result, indent=2), encoding='utf-8')
        print(json.dumps(result, indent=2))
    finally:
        transport.close()
