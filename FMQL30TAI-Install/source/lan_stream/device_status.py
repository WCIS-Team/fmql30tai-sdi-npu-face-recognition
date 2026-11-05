"""Diagnostic telemetry is independent of camera frames and model results."""
import re
import threading
import time
from collections import deque
from raw_protocol import decimal, integer


def validate_status(value):
    if not isinstance(value, dict) or type(value.get('schema_version')) is not int or value['schema_version'] != 1:
        raise ValueError('Invalid status schema')
    source = value.get('source')
    if source not in ('sdi_status_ddr', 'ps_capture'):
        raise ValueError('Invalid status source')
    boot = value.get('boot_id')
    if not isinstance(boot, str) or not re.fullmatch(r'[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}', boot):
        raise ValueError('Invalid boot identity')
    result = dict(schema_version=1, source=source, boot_id=boot)
    for key in ('sample_id', 'timestamp_us', 'status_sequence'):
        result[key] = decimal(value.get(key))
    for key in ('signal_locked', 'transport_locked', 'writer_fresh', 'progressive', 'qpll_locked'):
        if type(value.get(key)) is not bool and not (source == 'ps_capture' and value.get(key) is None):
            raise ValueError('Invalid status flag')
        result[key] = value[key]
    for key in ('width', 'height'):
        result[key] = integer(value.get(key), 0, 4096)
    result['capture_state'] = value.get('capture_state')
    allowed = ('blocked_incompatible_bitstream',) if source == 'sdi_status_ddr' else ('bridge_verified', 'capture_timeout')
    if result['capture_state'] not in allowed:
        raise ValueError('Unsupported capture state')
    passed = value.get('path_test_passed', False)
    if type(passed) is not bool or (source != 'ps_capture' and passed):
        raise ValueError('Invalid path-test evidence')
    result['path_test_passed'] = passed
    return result


class DeviceStatusHub:
    def __init__(self, stale_seconds=3):
        self.lock = threading.Lock()
        self.value = None
        self.arrival = 0
        self.stale_seconds = stale_seconds
        self.retired = deque(maxlen=32)

    def publish(self, value):
        value = validate_status(value)
        with self.lock:
            if value['boot_id'] in self.retired:
                raise LookupError('Retired boot')
            if self.value:
                if value['boot_id'] == self.value['boot_id']:
                    if int(value['sample_id']) <= int(self.value['sample_id']) or int(value['timestamp_us']) < int(self.value['timestamp_us']):
                        raise LookupError('Out-of-order status')
                else:
                    self.retired.append(self.value['boot_id'])
            self.value, self.arrival = value, time.monotonic()

    def status(self):
        with self.lock:
            age = time.monotonic() - self.arrival
            if self.value is None or age > self.stale_seconds:
                return dict(connected=False)
            return dict(self.value, connected=True, age_ms=round(age * 1000))
