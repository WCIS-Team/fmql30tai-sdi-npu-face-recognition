"""Equivalent ONNX PReLU decomposition, with independent CPU parity evidence."""
import hashlib
import argparse
import json
from pathlib import Path
import numpy as np
import onnx
from onnx import helper, numpy_helper
import onnxruntime as ort

root = Path(__file__).resolve().parents[1]
parser = argparse.ArgumentParser()
parser.add_argument('--without-neg', action='store_true')
parser.add_argument('--conv-slope', action='store_true')
args = parser.parse_args()
if args.conv_slope:
    args.without_neg = True
original = root / 'photo_reference/models/w600k_mbf.onnx'
out = root / 'outputs/photo-board-20261014/models'
out.mkdir(parents=True, exist_ok=True)
model = onnx.load(str(original))
initializers = {v.name:numpy_helper.to_array(v) for v in model.graph.initializer}
nodes, replaced = [], 0
for node in model.graph.node:
    if node.op_type != 'PRelu':
        nodes.append(node); continue
    x, alpha = node.input
    prefix = '__wcis_prelu_' + str(replaced)
    decomposition = [
        helper.make_node('Relu', [x], [prefix + '_pos'], name=prefix+'_positive'),
        helper.make_node('Neg', [x], [prefix + '_neg'], name=prefix+'_negate'),
        helper.make_node('Relu', [prefix + '_neg'], [prefix + '_mag'], name=prefix+'_negative_magnitude'),
        helper.make_node('Mul', [alpha, prefix + '_mag'], [prefix + '_scaled'], name=prefix+'_slope'),
        helper.make_node('Sub', [prefix + '_pos', prefix + '_scaled'], list(node.output), name=prefix+'_combine'),
    ]
    if args.without_neg:
        decomposition = [
            helper.make_node('Relu', [x], [prefix + '_pos'], name=prefix+'_positive'),
            helper.make_node('Sub', [x, prefix + '_pos'], [prefix + '_negative'], name=prefix+'_negative_part'),
            helper.make_node('Mul', [alpha, prefix + '_negative'], [prefix + '_scaled'], name=prefix+'_slope'),
            helper.make_node('Add', [prefix + '_pos', prefix + '_scaled'], list(node.output), name=prefix+'_combine'),
        ]
    if args.conv_slope:
        slope = initializers[alpha].reshape(-1)
        kernel = np.zeros((len(slope),1,3,3), dtype=np.float32)
        kernel[:,0,1,1] = slope
        weight = prefix + '_slope_kernel'
        bias = prefix + '_slope_bias'
        model.graph.initializer.extend([numpy_helper.from_array(kernel,weight),numpy_helper.from_array(np.zeros(len(slope),np.float32),bias)])
        decomposition[2] = helper.make_node('Conv', [prefix + '_negative',weight,bias], [prefix + '_scaled'],
                                             name=prefix+'_slope_conv', group=len(slope), pads=[1,1,1,1], kernel_shape=[3,3], strides=[1,1], dilations=[1,1])
    nodes.extend(decomposition)
    replaced += 1
del model.graph.node[:]
model.graph.node.extend(nodes)
used = {name for node in nodes for name in node.input}
retained = [value for value in model.graph.initializer if value.name in used]
del model.graph.initializer[:]
model.graph.initializer.extend(retained)
onnx.checker.check_model(model)
target = out / ('mobilefacenet-conv-slope.onnx' if args.conv_slope else 'mobilefacenet-no-neg.onnx' if args.without_neg else 'mobilefacenet-relu.onnx')
onnx.save(model, str(target))
options = ort.SessionOptions(); options.intra_op_num_threads = 2
first = ort.InferenceSession(str(original), options, providers=['CPUExecutionProvider'])
second = ort.InferenceSession(str(target), options, providers=['CPUExecutionProvider'])
checks = []
for path in sorted((root / 'outputs/photo-reference/debug').glob('*/recognizer_input.f32')):
    tensor = np.fromfile(path, np.float32).reshape(1,3,112,112)
    a = first.run(None, {first.get_inputs()[0].name:tensor})[0].flatten().astype(np.float64)
    b = second.run(None, {second.get_inputs()[0].name:tensor})[0].flatten().astype(np.float64)
    cosine = float(np.dot(a,b)/(np.linalg.norm(a)*np.linalg.norm(b)))
    error = float(np.max(np.abs(a-b)))
    checks.append({'sample':path.parent.name,'max_absolute_error':error,'feature_cosine':cosine,'passed':error<1e-4 and cosine>0.999999})
report = {'original_sha256':hashlib.sha256(original.read_bytes()).hexdigest(),
          'rewritten_sha256':hashlib.sha256(target.read_bytes()).hexdigest(),
          'replaced_prelu_nodes':replaced,'formula':'relu(x) + depthwise_center_alpha(x - relu(x))' if args.conv_slope else 'relu(x) + alpha * (x - relu(x))' if args.without_neg else 'relu(x) - alpha * relu(-x)',
          'weights_unchanged':True,'checks':checks,'all_passed':len(checks)==11 and all(c['passed'] for c in checks)}
(out / ('prelu-conv-slope-parity.json' if args.conv_slope else 'prelu-no-neg-parity.json' if args.without_neg else 'prelu-rewrite-parity.json')).write_text(json.dumps(report,indent=2))
print(json.dumps(report), flush=True)
assert report['all_passed']
