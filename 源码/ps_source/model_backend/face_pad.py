# Portions adapted from MiniVision / Zhu Ying, src/generate_patches.py.
# SPDX-License-Identifier: Apache-2.0
"""MiniFASNet input/output contract. No identity or unlocking policy.

Reference: minivision-ai/Silent-Face-Anti-Spoofing, commit
b6d5f04ad78778917853b25c778acef6d5626d15 (Apache-2.0).
The PL adapter operates in crop-local coordinates to replicate ROI edges.
"""
from dataclasses import dataclass
import numbers
import numpy as np

UPSTREAM_COMMIT = 'b6d5f04ad78778917853b25c778acef6d5626d15'
MODELS = (('MiniFASNetV2', 2.7, '2.7_80x80_MiniFASNetV2.pth'),
          ('MiniFASNetV1SE', 4.0, '4_0_0_80x80_MiniFASNetV1SE.pth'))


@dataclass(frozen=True)
class PadCrop:
    model: str
    left: int
    top: int
    width: int
    height: int

    def pl_command(self):
        """Q16.16 local inverse resize; addresses stay relative to full frame."""
        ax, ay = self.width / 80, self.height / 80
        return dict(roi=(self.left, self.top, self.width, self.height),
                    matrix=np.rint(np.array([[ax, 0, (ax-1)/2],
                                             [0, ay, (ay-1)/2]])*65536).astype(np.int64),
                    content=(80, 80), canvas=(80, 80), replicate=True, border=0)


def plan_crops(width, height, bbox_xywh):
    """Match upstream CropImage inclusive box + edge translation exactly.

    Reject invalid detector boxes rather than truncating or padding silently.
    Detector floating xywh coordinates must first be converted explicitly by
    its own adapter; this interface accepts original-frame integer xywh only.
    """
    values = (width, height, *bbox_xywh)
    if len(values) != 6 or any(isinstance(v, bool) or not isinstance(v, numbers.Integral) for v in values):
        raise ValueError('Expected integer source dimensions and xywh bbox')
    x, y, bw, bh = map(int, bbox_xywh)
    if not (2 <= width <= 8192 and 2 <= height <= 8192 and
            x >= 0 and y >= 0 and bw > 0 and bh > 0 and
            x+bw <= width and y+bh <= height):
        raise ValueError('Face box must fit the immutable original frame')
    crops = []
    for name, requested_scale, _ in MODELS:
        scale = min((height-1)/bh, (width-1)/bw, requested_scale)
        nw, nh = bw*scale, bh*scale
        cx, cy = bw/2+x, bh/2+y
        left, top, right, bottom = cx-nw/2, cy-nh/2, cx+nw/2, cy+nh/2
        if left < 0: right -= left; left = 0
        if top < 0: bottom -= top; top = 0
        if right > width-1: left -= right-width+1; right = width-1
        if bottom > height-1: top -= bottom-height+1; bottom = height-1
        left, top, right, bottom = map(int, (left, top, right, bottom))
        if not (0 <= left <= right < width and 0 <= top <= bottom < height):
            raise ValueError('Upstream crop geometry outside frame')
        crops.append(PadCrop(name, left, top, right-left+1, bottom-top+1))
    return tuple(crops)


def prepare_reference(image_bgr, bbox_xywh):
    """Official cv2 resize + BGR FP32 [0,255], NHWC file-tensor convention.

    Upstream functional.to_tensor does NOT divide numpy uint8 inputs by 255,
    despite its stale ToTensor docstring. Exported NCHW models transpose NHWC
    at the compiler boundary; channel order and magnitude stay unchanged.
    """
    import cv2
    image = np.asarray(image_bgr)
    if image.dtype != np.uint8 or image.ndim != 3 or image.shape[2] != 3:
        raise ValueError('Expected original uint8 BGR image')
    return {c.model: np.ascontiguousarray(cv2.resize(
        image[c.top:c.top+c.height, c.left:c.left+c.width], (80, 80)),
        dtype=np.float32)[None] for c in plan_crops(image.shape[1], image.shape[0], bbox_xywh)}


def combine_logits(logits_by_model):
    """Official two-model mean softmax. This is model evidence, not access.

    Missing/invalid models raise; callers must represent unavailable PAD, never
    replace it with a positive result. Scores are not calibrated probabilities
    of safe entry and must be bound to the same frame/face outside this module.
    """
    expected = {m[0] for m in MODELS}
    if set(logits_by_model) != expected:
        raise ValueError('Both official models are required exactly once')
    probs = []
    for name, _, _ in MODELS:
        v = np.asarray(logits_by_model[name], dtype=np.float64)
        if v.shape not in ((3,), (1, 3)) or not np.all(np.isfinite(v)):
            raise ValueError('Expected three finite logits per model')
        v = v.reshape(3); p = np.exp(v-v.max()); probs.append(p/p.sum())
    mean = np.mean(probs, axis=0)
    label = int(mean.argmax())
    return dict(model_label=label, model_predicts_live=label == 1,
                live_score=float(mean[1]), scores=mean.tolist(),
                calibrated=False)
