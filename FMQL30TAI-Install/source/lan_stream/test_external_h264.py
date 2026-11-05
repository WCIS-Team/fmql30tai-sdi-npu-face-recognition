import json
import os
from pathlib import Path
import tempfile
import threading
import unittest
from types import SimpleNamespace
from unittest.mock import patch, Mock
import external_h264
from external_h264 import Journal, ExternalH264


class JournalTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.path=Path(self.temp.name)/'raw-inputs.jsonl'
        self.path.touch();self.journal=Journal(self.path,limit=100)
        self.addCleanup(self.journal.close)
    def append(self,index,frame,at=100,synthetic=False):
        with self.path.open('a') as stream:
            stream.write(json.dumps(dict(input_index=index,frame_id=frame,captured_at=at,synthetic=synthetic))+'\n')
    def test_frame_selection_uses_capture_times_instead_of_nominal_pts(self):
        self.append(0,10,100);self.append(1,12,100.06);self.journal.update()
        capture=self.journal.capture(0,2,30)
        self.assertEqual(capture['first_frame'],10);self.assertEqual(capture['last_frame'],12)
        self.assertAlmostEqual(capture['end'],100.06+1/30)
    def test_missing_input_and_synthetic_video_are_not_admitted(self):
        self.append(0,0,synthetic=True);self.journal.update()
        self.assertIsNone(self.journal.capture(0,1,30))
        self.assertIsNone(self.journal.capture(1/30,1,30))
    def test_partial_publication_waits_for_newline(self):
        row=json.dumps(dict(input_index=0,frame_id=1,captured_at=100,synthetic=False))
        self.path.write_text(row[:20]);self.journal.update();self.assertFalse(self.journal.rows)
        with self.path.open('a') as stream:stream.write(row[20:]+'\n')
        self.journal.update();self.assertEqual(self.journal.capture(0,1,30)['first_frame'],1)
    def test_gaps_and_wrong_timestamp_cadence_are_rejected(self):
        self.append(0,1);self.append(2,3)
        with self.assertRaises(ValueError):self.journal.update()
        with self.assertRaises(ValueError):self.journal.capture(.01,1,30)
    @unittest.skipIf(os.name=='nt','The board uses POSIX rename semantics')
    def test_rotation_drains_old_inode_and_reads_new_file(self):
        self.append(0,1);self.journal.update();self.append(1,2,100.04)
        self.path.replace(self.path.with_suffix('.previous'));self.path.touch();self.append(2,3,100.08)
        self.journal.update();self.assertEqual(list(self.journal.rows),[0,1,2])
    def test_bounded_history_does_not_reuse_expired_frames(self):
        self.journal.limit=2
        for i in range(3):self.append(i,i+1,100+i/30)
        self.journal.update();self.assertIsNone(self.journal.capture(0,1,30))
        self.assertIsNotNone(self.journal.capture(1/30,2,30))

    def media_worker(self, numbers):
        worker=ExternalH264.__new__(ExternalH264)
        worker.work=Path(self.temp.name);worker.root=worker.work/'hls';worker.root.mkdir()
        worker.fps=30;worker.journal=self.journal
        worker.identity=dict(boot_id='boot',pid=10,session='test')
        worker.owner=SimpleNamespace(guard=lambda:None)
        worker.encoder=SimpleNamespace(poll=lambda:None,pid=11)
        worker.muxer=SimpleNamespace(poll=lambda:None,pid=12)
        worker.done_segments=set();worker.next_segment=0;worker.next_input=0
        worker.playlist_token=None;worker.playlist_changed=0
        worker.read_cache={};worker.published_media=None;worker.published_at=0
        (worker.root/'init.mp4').write_bytes(b'init')
        names=[f'seg-{n:09d}.m4s' for n in numbers]
        (worker.root/'index.m3u8').write_text('\n'.join(names))
        for name in names:(worker.root/name).write_bytes(b'fragment')
        return worker

    def test_fragment_sample_counts_survive_nominal_timestamp_drift(self):
        self.journal.limit=200
        for i in range(120):
            self.append(i,0 if i<60 else i-59,1000+(i-60)/30,i<60)
        worker=self.media_worker(range(4))
        with patch('external_h264.timing',side_effect=[(n*.99999,30) for n in range(4)]),patch('external_h264.time.monotonic',return_value=1003):
            worker._observe()
        media=json.loads((worker.work/'external-video.json').read_text())
        self.assertTrue(media['ready']);self.assertEqual(media['encoded'],60)
        self.assertEqual(media['frame_id'],60)
        self.assertFalse((worker.root/'seg-000000000.capture.json').exists())
        capture=json.loads((worker.root/'seg-000000002.capture.json').read_text())
        self.assertEqual(capture['first_index'],60);self.assertEqual(capture['start'],1000)

    def test_missing_fragment_is_not_mapped_to_wrong_camera_frame(self):
        for i in range(90):self.append(i,i+1,1000+i/30)
        worker=self.media_worker([0,2])
        with patch('external_h264.timing',return_value=(0,30)),patch('external_h264.time.monotonic',return_value=1003):
            with self.assertRaisesRegex(ValueError,'sequence is discontinuous'):worker._observe()

    def ready_worker(self):
        self.journal.limit=200
        for i in range(120):
            self.append(i,0 if i<60 else i-59,1000+(i-60)/30,i<60)
        return self.media_worker(range(4))

    def test_unchanged_poll_reuses_contents_but_refreshes_heartbeat(self):
        worker=self.ready_worker();counts={'reads':0}
        read_text,read_bytes=Path.read_text,Path.read_bytes
        def text(path,*args,**kwargs):
            counts['reads']+=1;return read_text(path,*args,**kwargs)
        def binary(path,*args,**kwargs):
            counts['reads']+=1;return read_bytes(path,*args,**kwargs)
        with patch('external_h264.timing',return_value=(0,30)),patch('external_h264.time.monotonic',return_value=1003) as clock,patch.object(Path,'read_text',text),patch.object(Path,'read_bytes',binary),patch('external_h264.atomic',wraps=external_h264.atomic) as write:
            worker._observe();first_reads=counts['reads'];first_writes=write.call_count
            clock.return_value=1003.2;worker._observe()
            self.assertEqual(counts['reads'],first_reads)
            self.assertEqual(write.call_count,first_writes)
            clock.return_value=1004.01;worker._observe()
            self.assertEqual(write.call_count,first_writes+2)
        self.assertEqual(json.loads((worker.work/'external-video.json').read_text())['updated_at'],1004.01)

    def test_cached_files_do_not_hide_deleted_segment_or_wrong_session(self):
        worker=self.ready_worker()
        with patch('external_h264.timing',return_value=(0,30)),patch('external_h264.time.monotonic',return_value=1003):
            worker._observe()
            segment=worker.root/'seg-000000003.m4s';segment.unlink()
            with self.assertRaises(FileNotFoundError):worker._observe()
            segment.write_bytes(b'fragment')
            metadata=segment.with_suffix('.capture.json')
            value=json.loads(metadata.read_text());value['session']='evil'
            replacement=metadata.with_suffix('.pending');replacement.write_text(json.dumps(value));replacement.replace(metadata)
            with self.assertRaisesRegex(ValueError,'another session'):worker._observe()

    def test_cached_poll_still_checks_owner_and_both_processes(self):
        worker=self.ready_worker()
        with patch('external_h264.timing',return_value=(0,30)),patch('external_h264.time.monotonic',return_value=1003):
            worker._observe()
            with patch.object(worker.owner,'guard',side_effect=RuntimeError('owner gone')):
                with self.assertRaisesRegex(RuntimeError,'owner gone'):worker._observe()
            for process in (worker.encoder,worker.muxer):
                with patch.object(process,'poll',return_value=1):
                    with self.assertRaisesRegex(RuntimeError,'worker exited'):worker._observe()

    def test_cache_never_extends_playlist_or_capture_freshness(self):
        worker=self.ready_worker()
        with patch('external_h264.timing',return_value=(0,30)),patch('external_h264.time.monotonic',return_value=1003) as clock:
            worker._observe();clock.return_value=1007.1
            with self.assertRaisesRegex(RuntimeError,'playlist is stale'):worker._observe()
            playlist=worker.root/'index.m3u8';pending=playlist.with_suffix('.pending')
            pending.write_bytes(playlist.read_bytes());pending.replace(playlist)
            with self.assertRaisesRegex(RuntimeError,'No fresh camera'):worker._observe()

    def test_delayed_journal_completes_without_playlist_change(self):
        self.journal.limit=200
        for i in range(90):self.append(i,0 if i<60 else i-59,1000+(i-60)/30,i<60)
        worker=self.media_worker(range(4))
        with patch('external_h264.timing',return_value=(0,30)),patch('external_h264.time.monotonic',return_value=1002.5):
            worker._observe();self.assertEqual(worker.next_input,90)
            for i in range(90,120):self.append(i,i-59,1000+(i-60)/30)
            worker._observe();self.assertEqual(worker.next_input,120)
            self.assertEqual(json.loads((worker.work/'external-video.json').read_text())['encoded'],60)

    def test_playlist_rotation_prunes_cache_and_publishes_new_frame(self):
        worker=self.ready_worker()
        with patch('external_h264.timing',return_value=(0,30)),patch('external_h264.time.monotonic',return_value=1003):
            worker._observe()
            for i in range(120,150):self.append(i,i-59,1000+(i-60)/30)
            (worker.root/'seg-000000004.m4s').write_bytes(b'next')
            playlist=worker.root/'index.m3u8';pending=playlist.with_suffix('.pending')
            pending.write_text('\n'.join(f'seg-{n:09d}.m4s' for n in range(3,5)));pending.replace(playlist)
            worker._observe()
            self.assertEqual(json.loads((worker.work/'external-video.json').read_text())['encoded'],90)
            self.assertLessEqual(len(worker.read_cache),4)
            self.assertNotIn(worker.root/'seg-000000002.capture.json',worker.read_cache)

    def test_recovery_republishes_immediately_after_failed_poll(self):
        worker=self.ready_worker()
        with patch('external_h264.timing',return_value=(0,30)),patch('external_h264.time.monotonic',return_value=1003):
            worker._observe()
            worker.error=None;worker.stop=Mock()
            worker.stop.is_set.side_effect=[False,False,True]
            worker.owner.guard=Mock(side_effect=[RuntimeError('temporary'),None])
            worker._monitor()
            self.assertTrue(json.loads((worker.work/'external-video.json').read_text())['ready'])
            self.assertIsNone(worker.error)

    @unittest.skipIf(os.name=='nt','The board uses POSIX FIFOs')
    def test_input_handshake_keeps_reader_alive_until_native_writes(self):
        worker=ExternalH264.__new__(ExternalH264)
        worker.fifo=Path(self.temp.name)/'input.fifo';os.mkfifo(worker.fifo)
        worker.encoder=SimpleNamespace(poll=lambda:None)
        worker.fifo_keeper=None;worker.keeper_lock=threading.Lock();received=[]
        def read():
            with worker.fifo.open('rb',buffering=0) as stream:received.append(stream.read(1))
        thread=threading.Thread(target=read,daemon=True);thread.start()
        worker._wait_reader()
        try:
            self.assertTrue(thread.is_alive(),'The handshake must not send EOF')
            native=os.open(worker.fifo,os.O_WRONLY|os.O_NONBLOCK)
            try:os.write(native,b'x')
            finally:os.close(native)
            worker._release_keeper();thread.join(timeout=2)
            self.assertEqual(received,[b'x']);self.assertFalse(thread.is_alive())
        finally:worker._release_keeper()


if __name__=='__main__':unittest.main()
