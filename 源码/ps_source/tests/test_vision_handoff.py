import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from vision_handoff import Handoff, UNITS, System, permit, dispatch


class MemoryStore:
    def __init__(self): self.q = None; self.history = []
    def load(self): return None if self.q is None else json.loads(json.dumps(self.q))
    def save(self, q): self.q = json.loads(json.dumps(q)); self.history.append(self.load())


class FakeSystem:
    def __init__(self):
        self.now = 10.; self.boot_id = 'boot'; self.states = {u: 'active' for u in UNITS}
        self.mode = 'auto'; self.frame = 100; self.pid = 50; self.stopped = []; self.started = []
        self.bad_close = False; self.quarantined = False; self.leftovers = False
        self.holds_lock = False; self.shutdown = False; self.fail_start = False; self.changed = False
        self.cfg = dict(app='/apps/current',release='/models',config_sha256='original',live_required=True)
        self.inhibited = False
        self.hashes = {u: u for u in UNITS}; self.calls = []
    def clock(self): return self.now
    def sleep(self, dt): self.now += dt
    def boot(self): return self.boot_id
    def safe_boot(self, b):
        if self.quarantined or b != self.boot_id: raise RuntimeError('quarantined or boot changed')
    def unit(self, u): return self.states[u]
    def config(self): return dict(self.cfg, config_sha256='changed') if self.changed else dict(self.cfg)
    def unit_hashes(self): return dict(self.hashes)
    def cgroup(self): return '/sys/fs/cgroup/systemd/system.slice/wcis-vision-voice.service'
    def owner(self, c, cfg): return dict(pid=c['pid'],session=c['session'],processes={'50':'old'},receipt='/receipt')
    def api(self, port, path, data=None):
        self.calls.append((port, path, data))
        if data is not None: self.mode = data['mode']; return dict(mode=self.mode)
        if path == '/api/health': return dict(status='ready',model_cache_ready=True,hardware_admission_ready=True,boot_id=self.boot_id)
        if port == 8093: return dict(mode=self.mode,state='idle',current=None,queue_bytes=0,error=None,source_ready=True)
        self.frame += 1
        if path.endswith('live-status'): return dict(ready=True,pid=self.pid,session='session')
        return dict(ready=True,boot_id=self.boot_id,pid=self.pid,session='session',frame_id=self.frame,encoded=self.frame,encoder_pid=51,muxer_pid=52)
    def stop(self, u): self.stopped.append(u); self.states[u] = 'inactive'; self.now += .5
    def start(self, *units):
        self.started.extend(units)
        if self.fail_start: raise RuntimeError('startup failed')
        for u in units: self.states[u] = 'active'
        self.pid = 60; self.now += 2
    def closed(self, q):
        if self.bad_close or any(v == 'active' for v in self.states.values()): raise RuntimeError('unsafe close')
        return dict(sdk_closed=True,camera_pending=False,exit_code=0)
    def locks_free(self, release):
        if self.holds_lock: raise RuntimeError('lock held')
    def task_gone(self, q):
        if self.leftovers: raise RuntimeError('voice remains')
    def stopping(self): return self.shutdown
    def hold(self, q): self.inhibited = True
    def release_hold(self, q, required=True):
        if not self.inhibited and required: raise RuntimeError('missing inhibitor')
        self.inhibited = False


class HandoffTests(unittest.TestCase):
    def setUp(self): self.s = FakeSystem(); self.store = MemoryStore(); self.h = Handoff(self.s,self.store)
    def paused(self): return self.h.pause('token','/voice/program')
    def test_normal_task_restores_auto_mode_and_measures_real_readiness(self):
        self.paused(); self.assertEqual(self.s.stopped,list(reversed(UNITS))); self.assertEqual(self.s.mode,'off')
        q=self.h.recover('token'); self.assertEqual(q['phase'],'restored'); self.assertEqual(self.s.mode,'auto')
        self.assertEqual(self.s.started,list(UNITS)); self.assertGreater(q['timing']['restore_seconds'],q['timing']['picture_seconds'])
        self.assertEqual(q['resumed_owner']['pid'],60)
        self.assertFalse(self.s.inhibited)
    def test_manual_and_off_modes_preserved(self):
        for mode in ('manual','off'):
            self.setUp();self.s.mode=mode;self.paused();self.h.recover('token');self.assertEqual(self.s.mode,mode)
    def test_supervisor_death_during_pause_finishes_safe_close_before_recovery(self):
        self.paused();q=self.store.load();q.update(phase='pausing',close_verified=False);self.store.save(q)
        self.h.recover('token');self.assertEqual(self.store.load()['phase'],'restored')
    def test_voice_nonzero_or_missing_completion_still_recovers(self):
        self.paused();q=self.store.load();q.update(phase='voice_running',voice_exit_code=7);self.store.save(q)
        self.h.recover('token');self.assertEqual(self.store.load()['phase'],'restored')
    def test_current_hardware_fault_never_restarts(self):
        self.paused();self.s.quarantined=True
        with self.assertRaises(RuntimeError):self.h.recover('token')
        self.assertFalse(self.s.started);self.assertEqual(self.store.load()['phase'],'blocked')
        self.assertTrue(self.s.inhibited)
    def test_bad_close_never_restarts_or_claims_pause_complete(self):
        self.s.bad_close=True
        with self.assertRaises(RuntimeError):self.paused()
        self.assertFalse(self.store.load()['close_verified']);self.assertFalse(self.s.started)
        with self.assertRaises(RuntimeError):self.h.recover('token')
        self.assertFalse(self.s.started)
    def test_live_voice_process_prevents_restore(self):
        self.paused();self.s.leftovers=True
        with self.assertRaisesRegex(RuntimeError,'voice remains'):self.h.recover('token')
        self.assertFalse(self.s.started)
    def test_foreign_hardware_lock_prevents_restore(self):
        self.paused();self.s.holds_lock=True
        with self.assertRaisesRegex(RuntimeError,'lock held'):self.h.recover('token')
        self.assertFalse(self.s.started)
    def test_boot_change_does_not_reuse_old_receipt(self):
        self.paused();self.s.boot_id='new'
        with self.assertRaisesRegex(RuntimeError,'Previous-boot'):self.h.recover('token')
        self.assertFalse(self.s.started);self.assertTrue(permit(self.store,'new'))
    def test_changed_application_or_units_prevents_restore(self):
        for kind in ('app','unit'):
            self.setUp();self.paused()
            if kind=='app':self.s.changed=True
            else:self.s.hashes[UNITS[0]]='changed'
            with self.assertRaisesRegex(RuntimeError,'configuration changed'):self.h.recover('token')
            self.assertFalse(self.s.started)
    def test_token_mismatch_cannot_resume_another_session(self):
        self.paused();self.assertEqual(self.h.recover('other')['action'],'no_matching_transaction');self.assertFalse(self.s.started)
    def test_recovery_idempotent(self):
        self.paused();self.h.recover('token');n=len(self.s.started);self.h.recover('token');self.assertEqual(n,len(self.s.started))
    def test_recovery_after_state_was_persisted_before_inhibitor_removal(self):
        self.paused();q=self.store.load();q['phase']='restoring';q['timing']['restore_started_at']=self.s.clock();self.store.save(q)
        self.h.recover('token');self.assertEqual(self.store.load()['phase'],'restored');self.assertFalse(self.s.inhibited)
    def test_shutdown_defers_to_normal_boot_instead_of_starting_devices(self):
        self.paused();self.s.shutdown=True;q=self.h.recover('token');self.assertEqual(q['phase'],'deferred_shutdown');self.assertFalse(self.s.started)
    def test_startup_failure_is_recorded_without_retry(self):
        self.paused();self.s.fail_start=True
        with self.assertRaises(RuntimeError):self.h.recover('token')
        self.assertEqual(self.store.load()['phase'],'blocked');self.assertEqual(len(self.s.started),1)
        with self.assertRaises(RuntimeError):self.h.recover('token')
        self.assertEqual(len(self.s.started),1)
        self.assertTrue(self.store.load()['restore_cleanup'])
    def test_incomplete_initial_services_rejected_without_stopping_anything(self):
        self.s.states[UNITS[1]]='inactive'
        with self.assertRaises(RuntimeError):self.paused()
        self.assertFalse(self.s.stopped);self.assertIsNone(self.store.load())
    def test_duplicate_session_does_not_replace_stop_evidence(self):
        self.paused();q=self.store.load()
        with self.assertRaises(RuntimeError):self.h.pause('new','/other')
        self.assertEqual(self.store.load(),q)
    def test_condition_blocks_active_and_failed_handoffs_but_allows_recovery(self):
        self.assertTrue(permit(self.store,'boot'));self.paused();self.assertFalse(permit(self.store,'boot'))
        q=self.store.load();q['phase']='blocked';self.store.save(q);self.assertFalse(permit(self.store,'boot'))
        q['phase']='restoring';self.store.save(q);self.assertTrue(permit(self.store,'boot'))
        q['phase']='restored';self.store.save(q);self.assertTrue(permit(self.store,'boot'))
    def test_dispatch_keeps_voice_arguments_out_of_systemd_expansion_and_logs(self):
        cmd=dispatch('a'*32)
        self.assertIn('--wait',cmd);self.assertEqual(cmd[-3:],['_run','--token','a'*32])
        self.assertTrue(any(x.startswith('--property=ExecStopPost=/usr/bin/python3 ') for x in cmd))
        self.assertIn('--property=SendSIGKILL=no',cmd)


class ReceiptTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.path=Path(self.temp.name)/'receipt.json'
        self.q=dict(boot_id='current',owner=dict(pid=50,receipt=str(self.path),processes={'50':'start','51':'enc','52':'mux'}))
        self.receipt=dict(boot_id='current',worker_pid=50,sdk_closed=True,camera_pending=False,sessions_released=True,exit_code=0)
        self.s=System();self.s.unit=lambda u:'inactive';self.s.process=lambda p:None
    def check(self):
        self.path.write_text(json.dumps(self.receipt));return self.s.closed(self.q)
    def test_normal_receipt_admits_only_the_exact_old_owner(self):self.assertTrue(self.check()['sdk_closed'])
    def test_wrong_boot_or_pid_and_incomplete_device_close_are_rejected(self):
        for key,value in [('boot_id','previous'),('worker_pid',49),('sdk_closed',False),('camera_pending',True),('sessions_released',False),('exit_code',1)]:
            with self.subTest(key=key):
                original=dict(self.receipt);self.receipt[key]=value
                with self.assertRaises(RuntimeError):self.check()
                self.receipt=original
    def test_surviving_encoder_or_owner_blocks_reopen(self):
        for pid,value in [(50,'start'),(51,'enc'),(52,'mux')]:
            self.s.process=lambda p: value if p==pid else None
            with self.assertRaisesRegex(RuntimeError,'still alive'):self.check()
    def test_an_active_visual_service_blocks_reopen_even_with_a_receipt(self):
        self.s.unit=lambda u:'active' if u==UNITS[0] else 'inactive'
        with self.assertRaisesRegex(RuntimeError,'did not stop'):self.check()


if __name__=='__main__':unittest.main()
