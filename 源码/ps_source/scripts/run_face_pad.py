"""Board-local explicit-bbox PAD probe, with no service/API/UI changes."""
import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--bundle',type=Path,required=True)
    p.add_argument('--image',type=Path,required=True)
    p.add_argument('--bbox',type=int,nargs=4,required=True,metavar=('X','Y','WIDTH','HEIGHT'))
    p.add_argument('--frame-id',type=int,required=True)
    p.add_argument('--out',type=Path,required=True)
    a=p.parse_args()
    from model_backend.face_pad_inference import predict
    result=predict(a.bundle,a.image,a.bbox,a.frame_id,a.out)
    print(json.dumps(result,ensure_ascii=False))


if __name__=='__main__':main()
