"""Run only the recognizer on one already recorded, valid NHWC input."""
from pathlib import Path
import argparse,json
from run_photos import Runner,save
import numpy as np
parser=argparse.ArgumentParser()
parser.add_argument('--root',type=Path,required=True)
args=parser.parse_args()
out=args.root/'recognizer-only';out.mkdir(exist_ok=False)
boot=Path('/proc/sys/kernel/random/boot_id').read_text().strip()
review=args.root.parents[1]/'hardware-review-required.json'
if review.exists() and json.loads(review.read_text()).get('boot_id')==boot:
    raise RuntimeError('Review previous failure before retry')
runner=Runner(args.root,out)
try:
    tensor=np.fromfile(args.root/'run-01/tensors/img1-mobilefacenet.f32',np.float32).reshape(112,112,3)
    raw,timing=runner.forward('mobilefacenet',tensor,'img1')
    save(out/'result.json',{'boot_id':boot,'timing':timing,'elements':len(raw[0]),'norm':float(np.linalg.norm(raw[0]))})
    print('Recognizer standalone output returned',len(raw[0]),flush=True)
except BaseException as error:
    save(review,{'boot_id':boot,'error_type':type(error).__name__,'message':str(error),'automatic_retry':False})
    raise
finally:
    runner.close()
