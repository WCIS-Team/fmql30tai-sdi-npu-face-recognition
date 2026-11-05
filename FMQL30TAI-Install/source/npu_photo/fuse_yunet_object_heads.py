"""Reparameterize six linear pointwise/spatial heads as dense convolutions.

The mathematical function is unchanged. Verify the exported logits on every
recorded CPU fixture before handing the candidate to the compiler.
"""
from pathlib import Path
import hashlib,json
import numpy as np
import onnx
from onnx import helper,numpy_helper
import onnxruntime as ort
root=Path(__file__).resolve().parents[1]
out=root/'outputs/photo-board-20261014/models'
source=out/'yunet-logits.onnx';model=onnx.load(str(source))
nodes={y:n for n in model.graph.node for y in n.output}
weights={v.name:numpy_helper.to_array(v) for v in model.graph.initializer}
replace={};remove=set();details=[]
for name in ['cls_8','cls_16','cls_32','obj_8','obj_16','obj_32']:
 node=nodes[name]
 while node.op_type!='Conv':node=nodes[node.input[0]]
 spatial=node;point=nodes[spatial.input[0]]
 assert point.op_type=='Conv'
 sa={a.name:helper.get_attribute_value(a) for a in spatial.attribute}
 pa={a.name:helper.get_attribute_value(a) for a in point.attribute}
 sw,pw=weights[spatial.input[1]],weights[point.input[1]]
 assert sw.shape==(1,1,3,3) and pw.shape[0]==1 and pw.shape[2:]==(1,1)
 assert sa.get('group',1)==1 and sa['pads']==[1,1,1,1] and sa['strides']==[1,1]
 assert pa.get('group',1)==1 and pa.get('strides',[1,1])==[1,1] and pa.get('pads',[0,0,0,0])==[0,0,0,0]
 assert sum(point.output[0] in n.input for n in model.graph.node)==1
 kernel=sw[0,0].astype(np.float64);point_bias=float(weights[point.input[2]][0])
 w=kernel[None,None,:,:]*pw[:,:,0,0,None,None].astype(np.float64)
 bias=weights[spatial.input[2]].astype(np.float64)+point_bias*kernel.sum()
 # The intermediate pointwise bias was zero-padded before spatial convolution.
 # A constant correction preserves the boundary exactly for the fixed 640 input.
 side=640//int(name.rsplit('_',1)[1]);correction=np.zeros((1,1,side,side),np.float32)
 for y in range(side):
  for x in range(side):
   valid=sum(kernel[ky,kx] for ky in range(3) for kx in range(3) if 0<=y+ky-1<side and 0<=x+kx-1<side)
   correction[0,0,y,x]=point_bias*(valid-kernel.sum())
 prefix='__wcis_head_dense_'+name
 model.graph.initializer.extend([numpy_helper.from_array(w.astype(np.float32),prefix+'_weight'),numpy_helper.from_array(bias.astype(np.float32),prefix+'_bias'),numpy_helper.from_array(correction,prefix+'_border')])
 sa['group']=1
 replace[spatial.name]=[helper.make_node('Conv',[point.input[0],prefix+'_weight',prefix+'_bias'],[prefix+'_dense'],name=prefix,**sa),helper.make_node('Add',[prefix+'_dense',prefix+'_border'],list(spatial.output),name=prefix+'_boundary')]
 remove.add(point.name);details.append({'output':name,'weight_shape':list(w.shape),'bias':bias.tolist(),'border_shape':list(correction.shape)})
new=[]
for n in model.graph.node:
 if n.name not in remove:new.extend(replace.get(n.name,[n]))
del model.graph.node[:];model.graph.node.extend(new)
used={name for node in new for name in node.input}
retained=[value for value in model.graph.initializer if value.name in used]
del model.graph.initializer[:];model.graph.initializer.extend(retained)
onnx.checker.check_model(model)
target=out/'yunet-dense-heads.onnx';onnx.save(model,str(target))
options=ort.SessionOptions();options.intra_op_num_threads=2
a=ort.InferenceSession(str(source),options,providers=['CPUExecutionProvider']);b=ort.InferenceSession(str(target),options,providers=['CPUExecutionProvider'])
checks=[]
for path in sorted((root/'outputs/photo-reference/debug').glob('*/detector_input.f32')):
 data=np.fromfile(path,np.float32).reshape(1,3,640,640)
 x=a.run(None,{a.get_inputs()[0].name:data});y=b.run(None,{b.get_inputs()[0].name:data})
 error=max(float(np.max(np.abs(i-j))) for i,j in zip(x,y))
 checks.append({'sample':path.parent.name,'max_error':error,'passed':error<1e-4})
report={'source_sha256':hashlib.sha256(source.read_bytes()).hexdigest(),'export_sha256':hashlib.sha256(target.read_bytes()).hexdigest(),'transformation':'pointwise 1x1 then single-channel spatial 3x3 becomes dense 3x3 plus exact border correction; fixed input 640','heads':details,'checks':checks,'all_passed':len(checks)==11 and all(c['passed'] for c in checks)}
(out/'dense-heads-parity.json').write_text(json.dumps(report,indent=2));print(json.dumps(report),flush=True)
assert report['all_passed']
