"""Expose detector logits for PS postprocessing; keep learned operators on NPU."""
from pathlib import Path
import hashlib
import json
import numpy as np
import onnx
import onnxruntime as ort
from onnx import helper

root=Path(__file__).resolve().parents[1]
original=root/'photo_reference/models/face_detection_yunet_2023mar.onnx'
out=root/'outputs/photo-board-20261014/models';out.mkdir(exist_ok=True)
model=onnx.load(str(original));names={v.name for v in model.graph.output}
nodes=[];removed=[]
for node in model.graph.node:
    if node.op_type=='Sigmoid' and node.output[0] in names:
        nodes.append(helper.make_node('Identity',list(node.input),list(node.output),name=node.name+'_PS_SIGMOID'))
        removed.append(node.output[0])
    else:nodes.append(node)
assert len(removed)==6
del model.graph.node[:];model.graph.node.extend(nodes)
onnx.checker.check_model(model)
target=out/'yunet-logits.onnx';onnx.save(model,str(target))
options=ort.SessionOptions();options.intra_op_num_threads=2
first=ort.InferenceSession(str(original),options,providers=['CPUExecutionProvider'])
second=ort.InferenceSession(str(target),options,providers=['CPUExecutionProvider'])
checks=[]
for path in sorted((root/'outputs/photo-reference/debug').glob('*/detector_input.f32')):
    tensor=np.fromfile(path,np.float32).reshape(1,3,640,640)
    a=first.run(None,{first.get_inputs()[0].name:tensor});b=second.run(None,{second.get_inputs()[0].name:tensor})
    for i,v in enumerate(second.get_outputs()):
        if v.name in removed:b[i]=1/(1+np.exp(-np.clip(b[i],-80,80)))
    error=max(float(np.max(np.abs(x-y))) for x,y in zip(a,b))
    checks.append({'sample':path.parent.name,'maximum_error':error,'passed':error<1e-6})
report={'original_sha256':hashlib.sha256(original.read_bytes()).hexdigest(),'export_sha256':hashlib.sha256(target.read_bytes()).hexdigest(),'host_sigmoid_outputs':removed,'weights_unchanged':True,'checks':checks,'all_passed':len(checks)==11 and all(c['passed'] for c in checks)}
(out/'yunet-logits-parity.json').write_text(json.dumps(report,indent=2));print(json.dumps(report),flush=True)
assert report['all_passed']
