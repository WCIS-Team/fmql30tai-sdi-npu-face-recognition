"""Wait for existing HTTP services and advancing H264 output. Read-only GETs."""
import argparse
import json
import time
from urllib.request import ProxyHandler, build_opener


def wait_ready(fetch, boot_id, timeout=45, clock=time.monotonic, sleep=time.sleep):
    if timeout <= 0 or not boot_id:
        raise ValueError('Positive timeout and expected boot ID are required')
    deadline = clock() + timeout
    baseline = None
    last_error = 'No response'
    attempts = 0
    while clock() < deadline:
        attempts += 1
        try:
            health = fetch('photo', '/api/health', deadline)
            camera = fetch('photo', '/api/camera/status', deadline)
            recorder = fetch('recorder', '/api/status', deadline)
            if not all(isinstance(q, dict) for q in (health, camera, recorder)):
                raise ValueError('Expected JSON status objects')
            healthy = (health.get('status') == 'ready' and health.get('model_cache_ready') is True
                       and health.get('hardware_admission_ready') is True
                       and health.get('boot_id') == boot_id and camera.get('boot_id') == boot_id
                       and camera.get('ready') is True and camera.get('codec') == 'h264'
                       and (camera.get('width'), camera.get('height')) == (960, 540)
                       and recorder.get('source_ready') is True and recorder.get('mode') == 'off'
                       and recorder.get('state') == 'idle' and recorder.get('current') is None
                       and recorder.get('error') is None)
            identity = (camera['boot_id'], camera['session'], camera['pid'])
            encoded = camera['encoded']
            frame = camera['frame_id']
            if not healthy or not camera['session'] or camera['pid'] <= 0 or type(encoded) is not int or type(frame) is not int:
                raise ValueError('Health, boot, media format or recording state is not ready')
            if baseline and baseline[0] == identity and encoded > baseline[1] and frame > baseline[2]:
                return dict(passed=True, scope='http_readiness_only', attempts=attempts,
                            boot_id=boot_id, camera=camera, recorder=recorder,
                            encoded_advance=encoded-baseline[1], frame_advance=frame-baseline[2])
            if baseline is None or baseline[0] != identity:
                baseline = (identity, encoded, frame)
            last_error = 'Waiting for advancing output in one owner session'
        except (OSError, ValueError, KeyError, TypeError) as error:
            baseline = None
            last_error = str(error)
        sleep(min(.25, max(0, deadline-clock())))
    return dict(passed=False, scope='http_readiness_only', attempts=attempts, error=last_error)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--photo-url', default='http://127.0.0.1:8091')
    p.add_argument('--recorder-url', default='http://127.0.0.1:8093')
    p.add_argument('--boot-id', required=True)
    p.add_argument('--timeout', type=float, default=45)
    args = p.parse_args()
    opener = build_opener(ProxyHandler({}))
    urls = dict(photo=args.photo_url.rstrip('/'), recorder=args.recorder_url.rstrip('/'))
    def fetch(service, path, deadline):
        remaining = deadline-time.monotonic()
        if remaining <= 0:
            raise TimeoutError('Readiness deadline reached')
        with opener.open(urls[service]+path, timeout=min(3, remaining)) as response:
            data = response.read(1024*1024+1)
            if len(data) > 1024*1024:
                raise ValueError('Status response exceeds limit')
            return json.loads(data)
    result = wait_ready(fetch, args.boot_id, args.timeout)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result['passed'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
