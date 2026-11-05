"""Locate the first numerical divergence using the same tensor and no board."""
from pathlib import Path
import json
import numpy as np
import onnxruntime as ort
from run_photos import decode
root=Path(__file__).resolve().parents[1]
folder=root/'outputs/redeploy-20261014/host-compare'
image=np.fromfile(root/'outputs/photo-board-20261014/recovered-yunet/input.f32',np.float32).reshape(1,640,640,3)
options=ort.SessionOptions();options.intra_op_num_threads=2
session=ort.InferenceSession(str(root/'outputs/photo-board-20261014/models/yunet-logits.onnx'),options,providers=['CPUExecutionProvider'])
reference=session.run(None,{session.get_inputs()[0].name:image.transpose(0,3,1,2)})
report={}
for stage in ['parse','optimize','quantize']:
 network=json.loads((folder/stage/'network.json').read_text())
 values=[o for o in network['ops'] if o['_type_key']=='icraft::xir::Output'][0]['inputs']
 stats=[]
 for i,(value,ref) in enumerate(zip(values,reference)):
  data=np.fromfile(folder/stage/'yunet/ftmpSFB'/(str(value['v_id'])+'.ftmp'),np.float32)
  ref=ref.flatten();assert len(data)==len(ref)
  stats.append({'output':i,'max_error':float(np.max(np.abs(data-ref))),'mean_error':float(np.mean(np.abs(data-ref))),'first':data[:4].tolist(),'reference_first':ref[:4].tolist()})
 data=[np.fromfile(folder/stage/'yunet/ftmpSFB'/(str(value['v_id'])+'.ftmp'),np.float32) for value in values]
 report[stage]={'face_count':len(decode(data,1,1,logits=True)),'stats':stats}
(folder/'comparison.json').write_text(json.dumps(report,indent=2));print(json.dumps(report),flush=True)
