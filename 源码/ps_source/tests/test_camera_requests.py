import concurrent.futures
import sys
import threading
import time
import unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'npu_photo'))
from camera_requests import CameraRequests


def response():
    return 200, {'entry': {'image': 'same-jpeg', 'result': {'camera_frame': {'frame_id': 12},
        'presentation_attack_detection': {'status': 'model_live', 'frame_age_ms': 100, 'max_age_ms': 3000}}}}


class CameraRequestTests(unittest.TestCase):
    def readers(self, queue, n):
        deadline=time.monotonic()+3
        while time.monotonic()<deadline:
            with queue.lock:
                if queue.current and queue.current['readers']==n:return
            time.sleep(.005)
        self.fail('Readers did not join')

    def test_overlapping_requests_share_but_next_request_is_fresh(self):
        queue=CameraRequests();gate=threading.Event();calls=[]
        def operation():calls.append(1);gate.wait(3);return response()
        with concurrent.futures.ThreadPoolExecutor(4) as pool:
            futures=[pool.submit(queue.run,operation) for _ in range(4)]
            try:self.readers(queue,4)
            finally:gate.set()
            results=[f.result() for f in futures]
        self.assertEqual(len(calls),1)
        self.assertEqual(sum(d['entry']['result']['camera_delivery']['shared'] for c,d in results),3)
        self.assertTrue(all(d['entry']['result']['camera_frame']['frame_id']==12 for c,d in results))
        results[0][1]['entry']['result']['camera_frame']['frame_id']=99
        self.assertEqual(results[1][1]['entry']['result']['camera_frame']['frame_id'],12)
        queue.run(operation);self.assertEqual(len(calls),2)

    def test_timeout_does_not_cancel_running_owner(self):
        queue=CameraRequests(timeout=.01);gate=threading.Event()
        with concurrent.futures.ThreadPoolExecutor(1) as pool:
            leader=pool.submit(queue.run,lambda:(gate.wait(3),response())[1]);self.readers(queue,1)
            self.assertEqual(queue.run(response)[0],503)
            self.assertIsNotNone(queue.current);gate.set();self.assertEqual(leader.result()[0],200)

    def test_bound_and_release(self):
        queue=CameraRequests(limit=1);gate=threading.Event()
        with concurrent.futures.ThreadPoolExecutor(1) as pool:
            leader=pool.submit(queue.run,lambda:(gate.wait(3),response())[1]);self.readers(queue,1)
            self.assertEqual(queue.run(response)[0],429)
            gate.set();leader.result()
        self.assertEqual(queue.run(response)[0],200)

    def test_delivery_delay_expires_pad(self):
        ticks=iter([0,1,5,5]);queue=CameraRequests(clock=lambda:next(ticks))
        code,data=queue.run(response)
        self.assertEqual(data['entry']['result']['presentation_attack_detection']['status'],'stale')

    def test_delivery_delay_expires_every_face_without_mutating_original(self):
        original=response()
        pad=original[1]['entry']['result']['presentation_attack_detection']
        pad.update(status='evaluated',evaluated_face_count=2,faces=[
            dict(face_index=i,status='model_live',frame_age_ms=100,max_age_ms=3000) for i in range(2)])
        ticks=iter([0,1,5,5]);queue=CameraRequests(clock=lambda:next(ticks))
        code,data=queue.run(lambda:original)
        actual=data['entry']['result']['presentation_attack_detection']
        self.assertEqual(actual['status'],'stale')
        self.assertEqual(actual['evaluated_face_count'],0)
        self.assertTrue(all(x['status']=='stale' and x['frame_age_ms']==4100 for x in actual['faces']))
        self.assertEqual(pad['faces'][0]['status'],'model_live')

    def test_error_does_not_leave_job_stuck(self):
        queue=CameraRequests()
        def fail():raise RuntimeError('test')
        with self.assertRaises(RuntimeError):queue.run(fail)
        self.assertIsNone(queue.current);self.assertEqual(queue.run(response)[0],200)

if __name__=='__main__':unittest.main()
