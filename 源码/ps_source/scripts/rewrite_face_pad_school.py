"""Exact PReLU decomposition for iCraft with independent ORT parity."""
import json
import os
from pathlib import Path
import sys


def main():
    root=Path(__file__).resolve().parent
    if not root.as_posix().lower().startswith('d:/yzd/tmp/wcis-face-pad-'):
        raise RuntimeError('Use the isolated school task')
    for key in ('TMP','TEMP','TMPDIR'):os.environ[key]=str(root/'scratch')
    os.environ['XDG_CACHE_HOME']=str(root/'cache')
    import numpy as np
    import onnx
    from onnx import helper,numpy_helper
    import onnxruntime as ort
    checks=[]
    options=ort.SessionOptions();options.intra_op_num_threads=2
    for role in ('MiniFASNetV2','MiniFASNetV1SE'):
        original=root/'models'/(role+'.onnx')
        model=onnx.load(str(original));nodes=[];replaced=0
        initializers={v.name:numpy_helper.to_array(v) for v in model.graph.initializer}
        # Export may express shared slopes through Identity nodes.
        for node in model.graph.node:
            if node.op_type=='Identity' and node.input[0] in initializers:
                initializers[node.output[0]]=initializers[node.input[0]]
        for node in model.graph.node:
            if node.op_type!='PRelu':nodes.append(node);continue
            x,alpha=node.input;prefix='__pad_prelu_'+str(replaced)
            slope=initializers[alpha].reshape(-1)
            kernel=np.zeros((len(slope),1,3,3),np.float32);kernel[:,0,1,1]=slope
            w,b=prefix+'_w',prefix+'_b'
            model.graph.initializer.extend([numpy_helper.from_array(kernel,w),numpy_helper.from_array(np.zeros(len(slope),np.float32),b)])
            nodes.extend([
                helper.make_node('Relu',[x],[prefix+'_pos'],name=prefix+'_positive'),
                helper.make_node('Sub',[x,prefix+'_pos'],[prefix+'_negative'],name=prefix+'_negative'),
                helper.make_node('Conv',[prefix+'_negative',w,b],[prefix+'_scaled'],name=prefix+'_slope',
                                 group=len(slope),pads=[1,1,1,1],kernel_shape=[3,3],strides=[1,1],dilations=[1,1]),
                helper.make_node('Add',[prefix+'_pos',prefix+'_scaled'],list(node.output),name=prefix+'_combine')])
            replaced+=1
        del model.graph.node[:];model.graph.node.extend(nodes)
        used={name for n in nodes for name in n.input}
        retained=[v for v in model.graph.initializer if v.name in used]
        del model.graph.initializer[:];model.graph.initializer.extend(retained)
        onnx.checker.check_model(model)
        target=root/'models'/(role+'-conv-slope.onnx');onnx.save(model,str(target))
        a=ort.InferenceSession(str(original),options,providers=['CPUExecutionProvider'])
        b=ort.InferenceSession(str(target),options,providers=['CPUExecutionProvider'])
        differences=[]
        for file in sorted((root/'models').glob(role+'-*.f32')):
            x=np.fromfile(file,dtype='<f4').reshape(1,80,80,3).transpose(0,3,1,2).copy()
            av=a.run(None,{'input':x})[0];bv=b.run(None,{'input':x})[0]
            np.testing.assert_allclose(av,bv,atol=1e-4,rtol=1e-4)
            differences.append({'sample':file.name,'max_abs_error':float(np.abs(av-bv).max())})
        assert len(differences)>=6 and replaced>0
        checks.append({'role':role,'replaced':replaced,'checks':differences,'passed':True})
    report={'passed':True,'formula':'relu(x) + depthwise_center_alpha(x-relu(x))',
            'se_blocks_preserved':True,'checks':checks}
    (root/'rewrite-parity.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
    print(json.dumps(report),flush=True)


if __name__=='__main__':main()
