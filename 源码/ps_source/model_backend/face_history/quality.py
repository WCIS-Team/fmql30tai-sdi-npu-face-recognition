"""Explainable image-quality heuristics, never identity or liveness scores."""
from dataclasses import asdict, dataclass
import hashlib
import json
import math

import cv2
import numpy as np


@dataclass(frozen=True)
class QualityPolicy:
    min_face_pixels: float = 40.0
    min_detection_score: float = 0.8
    min_laplacian_variance: float = 20.0
    min_brightness: float = 40.0
    max_brightness: float = 215.0
    max_clipped_fraction: float = 0.6
    max_truncated_fraction: float = 0.05
    thumbnail_size: int = 112

    def __post_init__(self):
        for name, value in asdict(self).items():
            if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
                raise ValueError('Invalid quality policy: ' + name)
        if self.min_face_pixels <= 0 or self.min_laplacian_variance <= 0:
            raise ValueError('Size and focus thresholds must be positive')
        if not 0 <= self.min_brightness < self.max_brightness <= 255:
            raise ValueError('Invalid brightness interval')
        if any(not 0 <= v <= 1 for v in (self.min_detection_score,
                self.max_clipped_fraction, self.max_truncated_fraction)):
            raise ValueError('Fractions must be between zero and one')
        if type(self.thumbnail_size) is not int or not 32 <= self.thumbnail_size <= 256:
            raise ValueError('Thumbnail size must be an integer in 32..256')

    @property
    def policy_id(self):
        raw = json.dumps(asdict(self), sort_keys=True, separators=(',', ':')).encode()
        return 'bbox-quality-v1:' + hashlib.sha256(raw).hexdigest()


def face_quality(image, face, policy=None):
    """Measure a clipped *source bbox*, independently of aligned crop borders.

    Focus is measured after fixed-size INTER_AREA resampling. Thresholds are
    provisional and must be calibrated for the capture domain. No pose or
    occlusion accuracy is inferred from five landmarks or detector confidence.
    """
    policy = policy or QualityPolicy()
    if (not isinstance(image, np.ndarray) or image.dtype != np.uint8 or
            image.ndim != 3 or image.shape[2] != 3 or not image.size):
        raise ValueError('Expected a nonempty uint8 BGR image')
    box = np.asarray(face.get('box'), dtype=np.float64)
    score = face.get('score')
    if box.shape != (4,) or not np.isfinite(box).all():
        raise ValueError('Expected a finite xyxy face box')
    if isinstance(score, bool) or not isinstance(score, (int, float)) or not math.isfinite(score) or not 0 <= score <= 1:
        raise ValueError('Invalid detection score')
    x1, y1, x2, y2 = box.tolist()
    if x2 <= x1 or y2 <= y1:
        raise ValueError('Face box must have positive area')
    height, width = image.shape[:2]
    left, top = max(0.0, x1), max(0.0, y1)
    right, bottom = min(float(width), x2), min(float(height), y2)
    if right <= left or bottom <= top:
        raise ValueError('Face box does not intersect the image')
    coverage = (right - left) * (bottom - top) / ((x2 - x1) * (y2 - y1))
    roi = image[int(math.floor(top)):int(math.ceil(bottom)),
                int(math.floor(left)):int(math.ceil(right))]
    gray = cv2.cvtColor(roi, cv2.COLOR_BGR2GRAY)
    thumbnail = cv2.resize(gray, (policy.thumbnail_size, policy.thumbnail_size),
                           interpolation=cv2.INTER_AREA)
    focus = float(cv2.Laplacian(thumbnail, cv2.CV_64F, ksize=1).var())
    brightness = float(gray.mean())
    dark = float(np.mean(gray <= 10))
    bright = float(np.mean(gray >= 245))
    metrics = dict(face_short_side_pixels=min(right - left, bottom - top),
                   detection_score=float(score), laplacian_variance=focus,
                   brightness_mean=brightness, dark_fraction=dark,
                   bright_fraction=bright, truncated_fraction=max(0.0, 1 - coverage))
    rules = [('face_too_small', metrics['face_short_side_pixels'] < policy.min_face_pixels),
             ('low_detection_score', score < policy.min_detection_score),
             ('low_detail_or_blur', focus < policy.min_laplacian_variance),
             ('too_dark', brightness < policy.min_brightness),
             ('too_bright', brightness > policy.max_brightness),
             ('excessive_clipping', dark + bright > policy.max_clipped_fraction),
             ('truncated_face', 1 - coverage > policy.max_truncated_fraction)]
    reasons = [name for name, failed in rules if failed]
    # Ranking only within explicitly supplied same-person candidates. It is
    # not a probability, learned FIQA score or evidence of identity equality.
    exposure = max(0.0, 1 - abs(brightness - 127.5) / 127.5)
    rank = (0.6 * min(focus / (policy.min_laplacian_variance * 10), 1.0) +
            0.25 * exposure + 0.15 * min(metrics['face_short_side_pixels'] / 160, 1.0))
    return dict(accepted=not reasons, reasons=reasons, metrics=metrics,
                heuristic_rank=float(rank), policy_id=policy.policy_id,
                measurement='source_bbox_gray_resized', calibrated=False)


def select_best(candidates):
    """Caller supplies one person's candidate group; rejected faces cannot win."""
    usable = [c for c in candidates if c['quality']['accepted']]
    return max(usable, key=lambda c: (c['quality']['heuristic_rank'],
               -c.get('sequence', 0), -c.get('face_index', 0))) if usable else None
