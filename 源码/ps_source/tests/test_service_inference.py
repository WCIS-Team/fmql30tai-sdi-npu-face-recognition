"""Exercise the actual service wrapper without starting its HTTP/SDK main."""
import ast
import copy
from pathlib import Path
from types import SimpleNamespace
import unittest


class InferenceWrapperTests(unittest.TestCase):
    def setUp(self):
        path=Path(__file__).resolve().parents[1]/'npu_photo/serve_photos.py'
        tree=ast.parse(path.read_text(encoding='utf-8'))
        function=next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name=='infer')
        code=compile(ast.Module(body=[function],type_ignores=[]),str(path),'exec')
        self.camera=dict(model_lifecycle='single_owner_cached_sessions',presentation_attack_detection=dict(status='evaluated',faces=[dict(face_index=0,status='model_live')]))
        self.photo=dict(model_lifecycle='resident_process_per_model')
        self.writes=[]
        self.jpeg=SimpleNamespace(read_bytes=lambda:b'same-frame-jpeg')
        self.context=dict(owner_frames=object(),model_backend=SimpleNamespace(
            infer_camera=lambda *args:(copy.deepcopy(self.camera),self.jpeg)),
            gallery=SimpleNamespace(templates=lambda:{}),
            recognize=lambda *args,**kwargs:copy.deepcopy(self.photo),
            args=SimpleNamespace(root=Path('/release'),pl_executable=Path('/owner')))
        exec(code,self.context)
        self.image=SimpleNamespace(write_bytes=self.writes.append)

    def test_camera_preserves_owner_lifecycle_and_per_face_evidence(self):
        for lifecycle in ('single_owner_cached_sessions','single_owner_cpu_models'):
            self.camera['model_lifecycle']=lifecycle
            q=self.context['infer'](self.image,Path('/request'),from_camera=True)
            self.assertEqual(q,self.camera)
        self.assertEqual(self.writes,[b'same-frame-jpeg']*2)

    def test_uploaded_photo_does_not_claim_camera_pad_or_cached_session(self):
        q=self.context['infer'](self.image,Path('/request'))
        self.assertEqual(q['model_lifecycle'],'single_owner_cpu_models')
        self.assertEqual(q['input_source'],'uploaded_photo')
        self.assertEqual(q['presentation_attack_detection']['status'],'not_evaluated')
        self.assertEqual(self.writes,[])


if __name__=='__main__':unittest.main()
