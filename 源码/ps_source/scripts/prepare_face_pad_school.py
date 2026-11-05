"""Run only inside an isolated school task with the pinned upstream checkout.

CPU reference inference, input-contract parity and ONNX export. No board access.
Use task-local python/ for OpenCV; never install into the shared environment.
"""
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import sys


def main():
    root = Path(__file__).resolve().parent
    if not root.as_posix().lower().startswith('d:/yzd/tmp/wcis-face-pad-'):
        raise RuntimeError('Upload this script into its isolated school task first')
    for key in ('TMP', 'TEMP', 'TMPDIR'):
        os.environ[key] = str(root/'scratch')
    for key in ('XDG_CACHE_HOME', 'TORCH_HOME', 'HF_HOME'):
        os.environ[key] = str(root/'cache')
    sys.path[:0] = [str(root/'python'), str(root/'reference'), str(root)]
    import numpy as np
    import cv2
    import torch
    import onnx
    import onnxruntime as ort
    import face_pad as adapter
    from src.anti_spoof_predict import AntiSpoofPredict, MODEL_MAPPING
    from src.generate_patches import CropImage
    from src.data_io.transform import ToTensor
    torch.set_num_threads(2)
    manifest = json.loads((root/'reference-manifest.json').read_text())
    if manifest['commit'] != adapter.UPSTREAM_COMMIT:
        raise RuntimeError('Unexpected upstream revision')
    for rel, digest in manifest['files'].items():
        if hashlib.sha256((root/'reference'/rel).read_bytes()).hexdigest() != digest:
            raise RuntimeError('Reference checksum changed: '+rel)
    os.chdir(root/'reference')  # Upstream detector uses relative model paths.
    predictor = AntiSpoofPredict(0)
    cropper = CropImage()
    generator = np.random.default_rng(20261018)
    geometry_checks = 0
    for _ in range(100):
        w, h = map(int, generator.integers(2, 1921, 2))
        bw, bh = int(generator.integers(1,w+1)), int(generator.integers(1,h+1))
        x, y = int(generator.integers(0,w-bw+1)), int(generator.integers(0,h-bh+1))
        for c, (_, scale, _) in zip(adapter.plan_crops(w,h,[x,y,bw,bh]), adapter.MODELS):
            box = cropper._get_new_box(w,h,[x,y,bw,bh],scale)
            assert box == (c.left,c.top,c.left+c.width-1,c.top+c.height-1)
            geometry_checks += 1
    inputs = {}; samples = []
    for path in sorted((root/'reference/images/sample').glob('*.jpg')):
        if path.stem.endswith('_result'): continue
        image = cv2.imread(str(path)); bbox = predictor.get_bbox(image)
        tensors = adapter.prepare_reference(image,bbox)
        for name, scale, weight in adapter.MODELS:
            official = cropper.crop(image,bbox,scale,80,80,True)
            official_tensor = ToTensor()(official).unsqueeze(0).numpy()
            ours = tensors[name].transpose(0,3,1,2)
            np.testing.assert_array_equal(official_tensor,ours)
            inputs[name,path.stem] = official_tensor.copy()
        samples.append({'name':path.stem,'bbox_xywh':bbox,
                        'source_sha256':hashlib.sha256(path.read_bytes()).hexdigest(),
                        'ground_truth':'upstream demo only; not an SDI security evaluation'})
    for name,_,_ in adapter.MODELS:
        for label, x in [('zeros',np.zeros((1,3,80,80),np.float32)),
                         ('white',np.full((1,3,80,80),255,np.float32)),
                         ('random',generator.uniform(0,255,(1,3,80,80)).astype(np.float32))]:
            inputs[name,label]=x
    checks=[]; result_models={}; outputs={}
    options=ort.SessionOptions();options.intra_op_num_threads=2;options.inter_op_num_threads=1
    for name,_,weight in adapter.MODELS:
        predictor._load_model(str(root/'reference/resources/anti_spoof_models'/weight))
        model=predictor.model.cpu().eval()
        target=root/'models'/(name+'.onnx')
        torch.onnx.export(model,torch.zeros((1,3,80,80)),str(target),
                          input_names=['input'],output_names=['logits'],
                          opset_version=11,dynamo=False)
        onnx.checker.check_model(onnx.load(str(target)))
        session=ort.InferenceSession(str(target),options,providers=['CPUExecutionProvider'])
        for (role,label),x in inputs.items():
            if role!=name:continue
            with torch.no_grad(): reference=model(torch.from_numpy(x)).numpy()
            actual=session.run(None,{'input':x})[0]
            diff=float(np.max(np.abs(actual-reference)))
            np.testing.assert_allclose(actual,reference,atol=1e-4,rtol=1e-4)
            nhwc=np.ascontiguousarray(x.transpose(0,2,3,1),dtype='<f4')
            file=root/'models'/(name+'-'+label+'.f32');nhwc.tofile(file)
            outputs.setdefault(label,{})[name]=reference.reshape(3).tolist()
            checks.append({'model':name,'sample':label,'max_abs_error':diff,'passed':True,
                           'input_file':file.name,'reference_logits':reference.reshape(3).tolist()})
        result_models[name]={'onnx_sha256':hashlib.sha256(target.read_bytes()).hexdigest(),
                             'weights_sha256':manifest['files']['resources/anti_spoof_models/'+weight]}
        print('EXPORTED',name,flush=True)
    report={'passed':True,'upstream_commit':manifest['commit'],
            'versions':{'torch':torch.__version__,'onnx':onnx.__version__,'ort':ort.__version__,'opencv':cv2.__version__},
            'input':'BGR FP32 [0,255]; PyTorch/ONNX NCHW, compiler boundary NHWC',
            'geometry_checks':geometry_checks,'exact_preprocessing_sample_count':len(samples),
            'models':result_models,'samples':samples,'checks':checks,
            'ensemble':{k:adapter.combine_logits(v) for k,v in outputs.items()},
            'board_accessed':False,'sdi_anti_spoof_effectiveness_tested':False}
    (root/'reference-parity.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
    print(json.dumps(report,indent=2),flush=True)


if __name__=='__main__':main()
