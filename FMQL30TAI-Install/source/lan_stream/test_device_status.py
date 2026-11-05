"""Exercise diagnostic freshness, ordering and separation from actual pixels."""
import http.client
import json
from pathlib import Path
import threading
import time
from device_status import DeviceStatusHub
from raw_protocol import RawHub
from server import FrameHub, ThreadingHTTPServer, handler_type
from sdi_status_sender import decode, SYNC_COMMAND


def main():
    hub = DeviceStatusHub(stale_seconds=.15)
    raw = RawHub()
    server = ThreadingHTTPServer(('127.0.0.1', 0), handler_type(FrameHub(), raw, hub))
    server.daemon_threads = True
    worker = threading.Thread(target=server.serve_forever, daemon=True)
    worker.start()

    def request(method, path, body=None):
        conn = http.client.HTTPConnection('127.0.0.1', server.server_port, timeout=2)
        try:
            conn.request(method, path, body)
            reply = conn.getresponse()
            return reply.status, reply.read()
        finally:
            conn.close()

    boot = 'ea7deb05-4703-4056-91f8-03fedac3727b'
    value = decode([0x53444953, 99, 0xa, 0, 8], boot, 1, 1, 98)
    checks = []
    try:
        assert int(SYNC_COMMAND, 16) == (64 | (2 << 2) | 1)
        assert value['writer_fresh'] and not value['signal_locked']
        assert not decode([0x53444953, 99, 0xa, 0, 8], boot, 2, 2, 99)['writer_fresh']
        try:
            decode([0, 99, 0xa, 0, 8], boot, 2, 2, 98)
            assert False
        except ValueError:
            pass
        checks.append('invalid magic/stopped PL writer cannot imply live signal')
        assert request('POST', '/api/device-status', json.dumps(value))[0] == 204
        state = json.loads(request('GET', '/api/status')[1])
        assert state['device']['connected'] and not state['live'] and state['frames_received'] == 0
        assert request('GET', '/api/frame')[0] == 503
        checks.append('real device telemetry never creates pixels or model results')
        assert request('POST', '/api/device-status', json.dumps(value))[0] == 409
        assert request('POST', '/api/device-status', json.dumps(dict(value, signal_locked=1)))[0] == 400
        newer = dict(value, sample_id='2', timestamp_us='2', writer_fresh=False)
        assert request('POST', '/api/device-status', json.dumps(newer))[0] == 204
        checks.append('replayed samples and malformed booleans rejected')
        new_boot = dict(newer, boot_id='ba7deb05-4703-4056-91f8-03fedac3727b', sample_id='1')
        assert request('POST', '/api/device-status', json.dumps(new_boot))[0] == 204
        assert request('POST', '/api/device-status', json.dumps(dict(newer, sample_id='3')))[0] == 409
        sdk = dict(new_boot, sample_id='2', source='ps_capture', capture_state='capture_timeout',path_test_passed=True,
                   signal_locked=None, transport_locked=None, writer_fresh=None, progressive=None, qpll_locked=None)
        assert request('POST', '/api/device-status', json.dumps(sdk))[0] == 204
        shown=json.loads(request('GET', '/api/status')[1])
        assert shown['device']['signal_locked'] is None and shown['device']['capture_state']=='capture_timeout'
        assert shown['device']['path_test_passed']
        assert request('GET','/api/frame')[0]==503 and shown['frames_received']==0
        assert request('POST','/api/device-status',json.dumps(dict(sdk,sample_id='3',source='sdi_status_ddr')))[0]==400
        checks.append('SDK trial receipt does not claim SDI lock or create a frame')
        time.sleep(.2)
        assert not json.loads(request('GET', '/api/status')[1])['device']['connected']
        checks.append('boot restart retirement and stale telemetry suppression')
        report = dict(passed=True, checks=checks, board_accessed=False)
        path = Path(__file__).resolve().parents[1]/'outputs/camera-preview/device-status-tests.json'
        path.write_text(json.dumps(report, indent=2), encoding='utf-8')
        print(json.dumps(report))
    finally:
        server.shutdown()
        server.server_close()
        worker.join(2)


if __name__ == '__main__':
    main()
