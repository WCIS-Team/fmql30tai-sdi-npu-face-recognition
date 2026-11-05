"""Coalesce overlapping camera reads; never reuse a completed request as a cache."""
import copy
import threading
import time


class CameraRequests:
    def __init__(self, limit=8, timeout=15, clock=time.monotonic):
        self.lock = threading.Lock()
        self.current = None
        self.limit, self.timeout, self.clock = limit, timeout, clock

    def run(self, operation):
        started = self.clock()
        with self.lock:
            job = self.current
            leader = job is None
            if leader:
                job = dict(done=threading.Event(), readers=0)
                self.current = job
            if job['readers'] >= self.limit:
                return 429, {'error': '摄像头等待请求过多，请稍后重试'}
            job['readers'] += 1
        try:
            if leader:
                try:
                    job['response'] = operation()
                except Exception:
                    job['response'] = (503, {'error': '摄像头检测失败，请查看服务日志'})
                    raise
                finally:
                    job['finished'] = self.clock()
                    with self.lock:
                        self.current = None
                        job['done'].set()
            elif not job['done'].wait(self.timeout):
                return 503, {'error': '等待本次摄像头检测超时，请稍后重试'}
            code, data = copy.deepcopy(job['response'])
            if code == 200:
                result = data['entry']['result']
                elapsed = max(0, self.clock()-job['finished'])*1000
                result['camera_delivery'] = dict(shared=not leader,
                    wait_ms=max(0, self.clock()-started)*1000, result_delivery_age_ms=elapsed)
                pad = result.get('presentation_attack_detection', {})
                for evidence in [pad]+pad.get('faces', []):
                    if isinstance(evidence.get('frame_age_ms'), (int, float)):
                        evidence['frame_age_ms'] += elapsed
                        if evidence['frame_age_ms'] > evidence.get('max_age_ms', 0):
                            evidence['status'] = 'stale'
                if pad.get('status') == 'stale':
                    pad['evaluated_face_count'] = 0
            return code, data
        finally:
            with self.lock:
                job['readers'] -= 1
