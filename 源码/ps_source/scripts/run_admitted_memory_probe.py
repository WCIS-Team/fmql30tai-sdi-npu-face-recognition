"""Board-side DDR admission using the existing SDK-allocation-only probe.

Run during maintenance after BOOT admission and before network/model SDK work.
It never stops an existing owner, guesses an address, or kills the SDK process.
"""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess

PROBE_BYTES = 1920 * 1080 * 2
ALLOCATION_BYTES = 64 + 1920 * 1080 * 4 + 64 + 8 * 1024 * 1024 + 64
WINDOW_BYTES = 128 * 1024 * 1024


def validate_probe(returncode, stdout):
    if returncode != 0:
        raise ValueError('DDR probe did not exit normally')
    lines = [line[len('WCIS_JPEG_RESULT '):] for line in stdout.splitlines()
             if line.startswith('WCIS_JPEG_RESULT ')]
    if len(lines) != 1:
        raise ValueError('Expected one complete DDR probe result')
    q = json.loads(lines[0])
    if q.get('status') != 'memory_probe' or q.get('customop_started') is not False:
        raise ValueError('Probe did not confirm the no-CustomOp contract')
    base = q.get('allocation_base')
    if type(base) is not int or base < 0 or base % 64 or base + ALLOCATION_BYTES > WINDOW_BYTES:
        raise ValueError('SDK allocation is outside the verified window')
    rows = q.get('results')
    if not isinstance(rows, list) or len(rows) != 4:
        raise ValueError('Expected all four offset/chunk cases')
    expected = {(offset, chunk) for offset in (0, 64) for chunk in (PROBE_BYTES, 65536)}
    seen = set()
    for row in rows:
        key = (row.get('offset'), row.get('chunk'))
        if key not in expected or key in seen or row.get('bytes') != PROBE_BYTES:
            raise ValueError('DDR probe coverage or transfer size is wrong')
        seen.add(key)
        for field in ('mismatches', 'second_read_mismatches', 'changed_between_reads'):
            if type(row.get(field)) is not int or row[field] != 0:
                raise ValueError('DDR data comparison failed: ' + field)
        for field, length in (('lane_errors', 64), ('bit_errors', 8)):
            values = row.get(field)
            if (not isinstance(values, list) or len(values) != length
                    or any(type(value) is not int or value != 0 for value in values)):
                raise ValueError('DDR error distribution is invalid: ' + field)
        if row.get('first_mismatch') != PROBE_BYTES:
            raise ValueError('DDR probe reported a mismatch position')
    return q


def main():
    import fcntl
    import os
    import signal

    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--expected-boot', required=True)
    p.add_argument('--boot-sha256', required=True)
    p.add_argument('--executable', type=Path, required=True)
    p.add_argument('--binary-sha256', required=True)
    p.add_argument('--library-path',
                   help='Optional reviewed runtime library directories, separated by colons')
    p.add_argument('--release', type=Path, required=True)
    p.add_argument('--output', type=Path, required=True)
    args = p.parse_args()
    boot = Path('/proc/sys/kernel/random/boot_id').read_text().strip()
    if boot != args.expected_boot:
        raise RuntimeError('Starting boot changed')
    proof = json.loads(Path('/root/wcis-face/candidates/face-camera-ready-20261020/live/boot-proof.json').read_text())
    if proof['boot_id'] != boot or proof['boot_files']['BOOT.bin'] != args.boot_sha256:
        raise RuntimeError('Actual BOOT has not been admitted')
    marker = Path('/root/wcis-face/hardware-review-required.json')
    if marker.exists() and json.loads(marker.read_text()).get('boot_id') == boot:
        raise RuntimeError('Hardware review is required for this boot')
    if hashlib.sha256(args.executable.read_bytes()).hexdigest() != args.binary_sha256:
        raise RuntimeError('Probe binary checksum mismatch')
    environment = os.environ.copy()
    if args.library_path is not None:
        libraries = args.library_path.split(':')
        if any(not value or not Path(value).is_absolute() or not Path(value).is_dir()
               for value in libraries):
            raise ValueError('Runtime library directories must exist and be absolute')
        environment['LD_LIBRARY_PATH'] = args.library_path
    stdout_path = args.output.with_suffix('.stdout.log')
    stderr_path = args.output.with_suffix('.stderr.log')
    if any(path.exists() for path in (args.output, stdout_path, stderr_path)):
        raise FileExistsError('Keep each preflight receipt in its own new path')
    args.output.parent.mkdir(parents=True, exist_ok=True)
    result = dict(passed=False, boot_id=boot, boot_sha256=args.boot_sha256,
                  binary_sha256=args.binary_sha256, customop_started=False,
                  library_path=args.library_path,
                  scope='One SDK allocation; not full DDR capacity or stability acceptance')
    locks = []
    ran = False
    handlers = {}
    try:
        for path in (args.release / 'npu.lock', Path('/root/wcis-camera-preview/camera.lock')):
            lock = path.open('a')
            locks.append(lock)
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        # A previous owner may have finished and quarantined the device between
        # the first guard and lock acquisition. Recheck before opening the SDK.
        locked_proof = json.loads(Path('/root/wcis-face/candidates/face-camera-ready-20261020/live/boot-proof.json').read_text())
        if (Path('/proc/sys/kernel/random/boot_id').read_text().strip() != boot
                or locked_proof['boot_id'] != boot
                or locked_proof['boot_files']['BOOT.bin'] != args.boot_sha256):
            raise RuntimeError('Startup admission changed before SDK access')
        if marker.exists() and json.loads(marker.read_text()).get('boot_id') == boot:
            raise RuntimeError('Hardware quarantine changed before SDK access')
        # Inherit the locks so a disconnected Python launcher cannot release
        # ownership while its isolated native child still has the device open.
        def deferred_signal(signum, _frame):
            result['termination_requested'] = signum
        for number in (signal.SIGTERM, signal.SIGINT):
            handlers[number] = signal.signal(number, deferred_signal)
        with stdout_path.open('xb') as out, stderr_path.open('xb') as err:
            child = subprocess.Popen([str(args.executable), '--memory-probe'],
                                     stdin=subprocess.DEVNULL, stdout=out, stderr=err,
                                     pass_fds=tuple(lock.fileno() for lock in locks),
                                     env=environment,
                                     start_new_session=True)
            ran = True
            result['pid'] = child.pid
            args.output.write_text(json.dumps(result, indent=2))
            result['exit_code'] = child.wait()  # No timeout kill or automatic retry.
        result['probe'] = validate_probe(result['exit_code'], stdout_path.read_text())
        if Path('/proc/sys/kernel/random/boot_id').read_text().strip() != boot:
            raise RuntimeError('Boot changed during the probe')
        result.update(passed=True, sdk_process_exited=True)
    except Exception as error:
        result['error'] = type(error).__name__ + ': ' + str(error)
        if ran:
            marker.write_text(json.dumps(dict(boot_id=boot, source='bounded_ddr_preflight',
                                             reason=result['error'], automatic_retry=False), indent=2))
        raise
    finally:
        for lock in locks:
            lock.close()
        for number, handler in handlers.items():
            signal.signal(number, handler)
        args.output.write_text(json.dumps(result, indent=2))


if __name__ == '__main__':
    main()
