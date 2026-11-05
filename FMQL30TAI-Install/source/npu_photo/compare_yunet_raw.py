"""Compare recovered hardware outputs with the exact recorded input on ORT."""
import json
from pathlib import Path
import sys
import numpy as np
import onnxruntime as ort
from run_photos import decode
root=Path(__file__).resolve().parents[1]
folder=root/'outputs/photo-board-20261014/recovered-yunet'
image=np.fromfile(folder/'input.f32',np.float32).reshape(1,640,640,3)
options=ort.SessionOptions();options.intra_op_num_threads=2
session=ort.InferenceSession(str(root/'photo_reference/models/face_detection_yunet_2023mar.onnx'),options,providers=['CPUExecutionProvider'])
actual=[np.fromfile(folder/(str(i)+'.f32'),np.float32) for i in range(12)]
reference=session.run(None,{session.get_inputs()[0].name:image.transpose(0,3,1,2)})
stats=[]
for i,(a,b) in enumerate(zip(actual,reference)):
    b=b.flatten();stats.append({'output':i,'max_absolute_error':float(np.max(np.abs(a-b))), 'mean_absolute_error':float(np.mean(np.abs(a-b))), 'cpu_first':b[:8].tolist(),'npu_first':a[:8].tolist()})
report={'cpu_faces':len(decode([v.flatten() for v in reference],1,1)),'npu_faces':len(decode(actual,1,1)),'stats':stats}
(folder/'comparison.json').write_text(json.dumps(report,indent=2))
print(json.dumps(report),flush=True)
