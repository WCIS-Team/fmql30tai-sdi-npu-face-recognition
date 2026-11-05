"""Small CPU runtime checks; no project/model/audio entrypoints are executed."""
from pathlib import Path
import importlib.metadata as metadata
import importlib
import json
import sys
import traceback

root = Path(sys.argv[1]).resolve()
assert str(root).replace('\\', '/').lower().startswith('d:/yzd/tmp/')
result = {'executable':sys.executable, 'checks':{}}
for name in ('numpy', 'onnx', 'torch', 'onnxruntime'):
    try:
        metadata.version(name)
    except metadata.PackageNotFoundError:
        result['checks'][name] = {'status':'not_installed'}
        continue
    try:
        module = importlib.import_module(name)
        entry = {'status':'passed', 'version':module.__version__}
        if name == 'numpy':
            assert (module.array([1.,2.],dtype=module.float32)+1).tolist() == [2.,3.]
            entry['test'] = 'float32 vector addition'
        elif name == 'torch':
            assert (module.tensor([1.,2.], device='cpu')+1).tolist() == [2.,3.]
            entry['test'] = 'CPU tensor addition'
        elif name == 'onnx':
            from onnx import helper, TensorProto
            graph = helper.make_graph([
                helper.make_node('Add', ['x','one'], ['y'])], 'runtime_probe',
                [helper.make_tensor_value_info('x',TensorProto.FLOAT,[2])],
                [helper.make_tensor_value_info('y',TensorProto.FLOAT,[2])],
                [helper.make_tensor('one',TensorProto.FLOAT,[1],[1.])])
            model = helper.make_model(graph, opset_imports=[helper.make_opsetid('',13)])
            model.ir_version = 9
            module.checker.check_model(model)
            module.save(model, str(root / 'tiny_add.onnx'))
            entry['test'] = 'IR9 Add graph construction/checker'
        else:
            import numpy as np
            session = module.InferenceSession(str(root / 'tiny_add.onnx'), providers=['CPUExecutionProvider'])
            assert session.run(None, {'x':np.array([1.,2.],dtype=np.float32)})[0].tolist() == [2.,3.]
            entry['providers'] = module.get_available_providers()
            entry['test'] = 'CPU ONNX Add inference'
        result['checks'][name] = entry
    except Exception as error:
        result['checks'][name] = {'status':'failed','error':str(error),'type':type(error).__name__}
print(json.dumps(result, ensure_ascii=True))
name = Path(sys.executable).parent.parent.name + '-runtime.json'
(root / name).write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding='utf-8')
