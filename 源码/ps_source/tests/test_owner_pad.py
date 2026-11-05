"""CPU-only contract tests; fake owner replies do not prove NPU execution."""
import copy
import hashlib
import json
import os
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import numpy as np
ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT),str(ROOT/'npu_photo')]
from owner_pad import evaluate, checked_bundle, expand_rgb565
from model_backend.face_pad import MODELS, UPSTREAM_COMMIT


class PadTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.raw=Path(self.temp.name)/'source.rgb565'
        values=np.arange(960*540,dtype=np.uint16);self.raw.write_bytes(values.astype('<u2').tobytes())
        self.frame=dict(frame_id=17,boot_id='boot',pid=42,session='trial',width=960,height=540,
                        captured_at=100.,input_pixel_format='RGB565LE',source_rgb565_sha256=hashlib.sha256(self.raw.read_bytes()).hexdigest())
        face=dict(box=[120.2,100.3,210.1,220.7],score=.9)
        self.result=dict(camera_frame=copy.deepcopy(self.frame),boot_id='boot',source_rgb565_sha256=self.frame['source_rgb565_sha256'],
                         faces=[face],face_count=1,identities=[dict(face_index=0,face=face,status='recognized')])
        self.lease=dict(frame_id=17,boot_id='boot',frame_token='lease')
        self.pre=SimpleNamespace(retained_frame=self.lease,verify_retained_source=lambda:dict(full_source_equal=True))
        self.calls=[];self.stems=[];self.logits=[-2.,4.,-1.];self.bad_reply={};self.now=100.5
        def forward(role,data,out,stem,retained_frame):
            self.calls.append((role,data.copy()))
            self.stems.append(stem)
            reply=dict(role=role,single_owner=True,frame_id=17,frame_token='lease',worker_pid=42,
                       frame_preserved=True,npu_bound_ops=10,device_closed=False)
            reply.update(self.bad_reply)
            return [np.array(self.logits)],reply
        self.owner=SimpleNamespace(boot='boot',process=SimpleNamespace(pid=42),work=Path('/dev/shm/wcis-owner-trial'),forward=forward)

    def run_pad(self,**kwargs):
        return evaluate(self.owner,self.pre,self.result,self.raw,self.frame,Path(self.temp.name),clock=kwargs.pop('clock',lambda:self.now),**kwargs)

    def group(self, count):
        self.result['faces']=[dict(box=[30+i*100,60,100+i*100,160],score=.99-i*.01) for i in range(count)]
        self.result['face_count']=count
        self.result['identities']=[dict(face_index=i,face=self.result['faces'][i],status='recognized' if i%2==0 else 'unknown')
                                   for i in reversed(range(min(count,4)))]

    def test_same_frame_live_and_exact_reference_pixels(self):
        result=self.run_pad()
        self.assertEqual(result['status'],'model_live');self.assertFalse(result['security_calibrated'])
        self.assertEqual(result['authorization'],'not_evaluated');self.assertEqual(result['bbox_xywh'],[120,100,91,121])
        self.assertEqual([x[0] for x in self.calls],[m[0] for m in MODELS])
        from model_backend.face_pad import prepare_reference
        packed=np.frombuffer(self.raw.read_bytes(),'<u2').reshape(540,960)
        b=packed&31;g=(packed>>5)&63;r=packed>>11
        expected=np.stack([(b<<3)|(b>>2),(g<<2)|(g>>4),(r<<3)|(r>>2)],axis=2).astype(np.uint8)
        reference=prepare_reference(expected,[120,100,91,121])
        for role,data in self.calls:np.testing.assert_array_equal(data,reference[role])

    def test_nonlive(self):
        self.logits=[5.,-1.,0.];self.assertEqual(self.run_pad()['status'],'model_non_live')

    def test_tied_output_is_inconclusive(self):
        self.logits=[0.,0.,0.];self.assertEqual(self.run_pad()['status'],'inconclusive')

    def test_no_face_does_not_run_pad(self):
        self.group(0)
        result=self.run_pad()
        self.assertEqual(result['status'],'not_applicable')
        self.assertEqual(result['reason'],'no_face')
        self.assertEqual(result['faces'],[])
        self.assertEqual(self.calls,[])

    def test_four_faces_match_each_crop_and_keep_identity_indices(self):
        from model_backend.face_pad import prepare_reference
        self.group(4)
        result=self.run_pad()
        self.assertEqual(result['status'],'evaluated')
        self.assertEqual(result['processed_face_count'],4)
        self.assertEqual(result['evaluated_face_count'],4)
        self.assertNotIn('model_result',result)
        self.assertEqual(len(self.calls),8)
        packed=np.frombuffer(self.raw.read_bytes(),'<u2').reshape(540,960)
        b=packed&31;g=(packed>>5)&63;r=packed>>11
        image=np.stack([(b<<3)|(b>>2),(g<<2)|(g>>4),(r<<3)|(r>>2)],axis=2).astype(np.uint8)
        for call,person in enumerate(self.result['identities']):
            index=person['face_index'];item=result['faces'][index]
            self.assertEqual(item['identity_status'],person['status'])
            expected=prepare_reference(image,item['bbox_xywh'])
            for j,(role,_,_) in enumerate(MODELS):
                self.assertEqual(self.calls[call*2+j][0],role)
                np.testing.assert_array_equal(self.calls[call*2+j][1],expected[role])
                self.assertEqual(self.stems[call*2+j],'pad-face-'+str(index))
        self.assertTrue(all(v>=0 for v in result['aggregate_timing_ms'].values()))

    def test_live_and_attack_faces_are_not_collapsed_into_one_verdict(self):
        self.group(2);forward=self.owner.forward
        def mixed(role,data,out,stem,retained_frame):
            self.logits=[-2.,4.,-1.] if stem=='pad-face-0' else [5.,-1.,0.]
            return forward(role,data,out,stem,retained_frame)
        self.owner.forward=mixed
        result=self.run_pad()
        self.assertEqual(result['status'],'evaluated')
        self.assertEqual([x['status'] for x in result['faces']],['model_live','model_non_live'])
        self.assertNotIn('models',result)

    def test_five_faces_only_run_four_selected_identities(self):
        self.group(5)
        # The detector's highest-score selection need not be detection order.
        self.result['identities'][0]=dict(face_index=4,face=self.result['faces'][4],status='unknown')
        result=self.run_pad()
        self.assertEqual(result['status'],'partial')
        self.assertEqual(result['processed_face_count'],4)
        self.assertEqual(result['skipped_face_count'],1)
        self.assertEqual(result['faces'][3]['reason'],'face_limit')
        self.assertEqual(result['faces'][4]['status'],'model_live')
        self.assertEqual(len(self.calls),8)

    def test_duplicate_missing_and_wrong_identity_binding_rejected_before_inference(self):
        for change in ('duplicate','missing','wrong_face','negative','boolean'):
            self.group(2)
            if change=='duplicate':self.result['identities'][1]=copy.deepcopy(self.result['identities'][0])
            elif change=='missing':self.result['identities'].pop()
            elif change=='wrong_face':self.result['identities'][0]['face']=self.result['faces'][0]
            elif change=='negative':self.result['identities'][0]['face_index']=-1
            else:self.result['identities'][0]['face_index']=True
            with self.subTest(change=change),self.assertRaises(RuntimeError):self.run_pad()
        self.assertEqual(self.calls,[])

    def test_foreign_frame_session_boot_and_owner_rejected(self):
        for key,value in [('frame_id',18),('session','other'),('boot_id','other'),('pid',43)]:
            with self.subTest(key=key):
                old=self.frame[key];self.frame[key]=value
                with self.assertRaises(RuntimeError):self.run_pad()
                self.frame[key]=old

    def test_old_or_future_frame_is_not_run(self):
        for now in (104.,99.):self.assertEqual(self.run_pad(clock=lambda:now)['status'],'stale')
        self.assertEqual(self.calls,[])

    def test_frame_expiring_during_forward_has_no_live_status(self):
        self.group(4);forward=self.owner.forward
        def expiring(*args,**kwargs):
            answer=forward(*args,**kwargs);self.now=104.;return answer
        self.owner.forward=expiring
        result=self.run_pad()
        self.assertEqual(result['status'],'stale')
        self.assertEqual(len(self.calls),1)
        self.assertTrue(all(x['status']=='stale' for x in result['faces']))
        self.assertEqual(result['evaluated_face_count'],0)

    def test_frame_expiring_during_source_verification_invalidates_finished_faces(self):
        self.group(2)
        def verify():self.now=104.;return dict(full_source_equal=True)
        self.pre.verify_retained_source=verify
        result=self.run_pad()
        self.assertEqual(result['processed_face_count'],2)
        self.assertEqual(result['evaluated_face_count'],0)
        self.assertTrue(all(x['status']=='stale' for x in result['faces']))

    def test_source_is_decoded_once_for_a_group(self):
        self.group(4)
        with patch('owner_pad.expand_rgb565',wraps=expand_rgb565) as expand:
            self.run_pad()
        self.assertEqual(expand.call_count,1)

    def test_all_rgb565_values_match_bit_replication_and_frames_are_independent(self):
        packed=np.arange(65536,dtype='<u2').reshape(256,256)
        b=packed&31;g=(packed>>5)&63;r=packed>>11
        expected=np.stack([(b<<3)|(b>>2),(g<<2)|(g>>4),(r<<3)|(r>>2)],axis=2).astype(np.uint8)
        first=expand_rgb565(packed)
        np.testing.assert_array_equal(first,expected)
        self.assertEqual(first.dtype,np.uint8)
        self.assertTrue(first.flags.c_contiguous)
        first[:]=0
        np.testing.assert_array_equal(expand_rgb565(packed),expected)

    def test_changed_raw_and_wrong_face_binding_rejected(self):
        self.raw.write_bytes(bytes(960*540*2))
        with self.assertRaises(RuntimeError):self.run_pad()
        self.result['identities'][0]['face_index']=1
        with self.assertRaises(RuntimeError):self.run_pad()
        self.assertEqual(self.calls,[])

    def test_wrong_receipt_and_missing_npu_execution_rejected(self):
        for bad in (dict(role='other'),dict(frame_id=18),dict(frame_token='old'),dict(worker_pid=2),dict(npu_bound_ops=0),dict(device_closed=True)):
            with self.subTest(bad=bad):
                self.bad_reply=bad
                with self.assertRaises(RuntimeError):self.run_pad()

    def test_nonfinite_output_and_hardware_error_propagate(self):
        self.logits=[0.,float('nan'),0.]
        with self.assertRaises(ValueError):self.run_pad()
        self.owner.forward=lambda *a,**k:(_ for _ in ()).throw(TimeoutError('SDK deadline'))
        with self.assertRaises(TimeoutError):self.run_pad()

    def test_ddr_corruption_rejected(self):
        self.pre.verify_retained_source=lambda:dict(full_source_equal=False)
        with self.assertRaises(RuntimeError):self.run_pad()

    def test_invalid_box(self):
        for box in ([1,1,float('nan'),4],[5,2,1,3],[-5,-4,-1,-1]):
            self.result['faces'][0]['box']=box
            with self.assertRaises(ValueError):self.run_pad()

    def test_bundle_coverage_hash_and_path(self):
        bundle=Path(self.temp.name)/'bundle';bundle.mkdir()
        manifest=dict(generated=True,upstream_commit=UPSTREAM_COMMIT,models={},files_sha256={})
        for role,_,_ in MODELS:
            manifest['models'][role]={}
            for key in ('json','raw'):
                name=role+'.'+key;path=bundle/name;path.write_bytes(b'test')
                manifest['models'][role][key]=name;manifest['files_sha256'][name]=hashlib.sha256(b'test').hexdigest()
        m=bundle/'pad-models.json';m.write_text(json.dumps(manifest));self.assertEqual(len(checked_bundle(bundle)[2]),5)
        first=MODELS[0][0]+'.json';(bundle/first).write_bytes(b'changed')
        with self.assertRaises(ValueError):checked_bundle(bundle)
        manifest['models'][MODELS[0][0]]['json']='../outside.json';m.write_text(json.dumps(manifest))
        with self.assertRaises(ValueError):checked_bundle(bundle)

    @unittest.skipIf(os.name == 'nt', 'CameraOwner requires Linux fcntl and pipe polling')
    def test_stop_receipt_survives_full_diagnostic_log(self):
        import io,os,queue
        from camera_owner_runtime import CameraOwner
        owner=CameraOwner.__new__(CameraOwner)
        read_fd,write_fd=os.pipe();stream=os.fdopen(read_fd,'rb')
        self.addCleanup(stream.close)
        receipt=dict(status='stopped',sdk_closed=True,camera_pending=False)
        os.write(write_fd,('WCIS_OWNER_RESULT '+json.dumps(receipt)+'\n').encode());os.close(write_fd)
        owner.process=SimpleNamespace(stdout=stream);owner.logged=4*1024*1024;owner.log=io.BytesIO()
        owner.buffer=b'';owner.responses=queue.Queue(maxsize=2);owner.stopping=True;owner.stop_receipt=None
        owner._pump()
        self.assertEqual(owner.stop_receipt,receipt);self.assertEqual(owner.log.getvalue(),b'')


if __name__=='__main__':unittest.main(verbosity=2)
