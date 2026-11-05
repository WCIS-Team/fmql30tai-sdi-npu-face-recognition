"""Geometry-only ModelBackend descriptors; no inference/identity scheduling.

Reference: InsightFace utils/face_align.py estimate_norm (MIT), OpenCV resize
half-pixel mapping and invertAffineTransform. Existing deployed code is untouched.
"""
import numpy as np
import cv2

ARCFACE_DST = np.array([[38.2946, 51.6963], [73.5318, 51.5014],
                       [56.0252, 71.7366], [41.5493, 92.3655],
                       [70.7299, 92.2041]], dtype=np.float32)


def inverse_q16(matrix):
    """Quantize an output->source 2x3 matrix, rejecting overflow/nonfinite."""
    matrix = np.asarray(matrix, dtype=np.float64)
    if matrix.shape != (2, 3) or not np.all(np.isfinite(matrix)):
        raise ValueError('Expected a finite inverse 2x3 matrix')
    values = np.rint(matrix * 65536)
    if np.any(values < -(2**31)) or np.any(values >= 2**31):
        raise ValueError('Transform exceeds signed Q16.16')
    return values.astype(np.int64)


def detector_geometry(width, height):
    """Match the deployed YuNet canvas: full view, top-left, BLACK padding.

    An approximate 1/32 pixel interpolation grid is a separate acceptance gate
    for noninteger resizes; do not silently replace the deployed cv2.resize.
    """
    if not (1 <= width <= 8192 and 1 <= height <= 8192):
        raise ValueError('Source dimensions outside RTL contract')
    ratio = min(640 / width, 640 / height)
    cw, ch = max(1, int(width * ratio)), max(1, int(height * ratio))
    ax, ay = width / cw, height / ch
    inverse = np.array([[ax, 0, (ax - 1) / 2], [0, ay, (ay - 1) / 2]])
    return dict(content=(cw, ch), canvas=(640, 640),
                matrix=inverse_q16(inverse), replicate=True, border=0,
                scale=(cw / width, ch / height))


def face_geometry(landmarks):
    """Use the same similarity estimator as InsightFace, without RANSAC.

    Lazy import: detector-only use does not require scikit-image. Source points
    must be in the coordinates of the retained original frame, in detector eye,
    nose and mouth order matching ARCFACE_DST; never a later camera frame.
    """
    from skimage.transform import SimilarityTransform
    points = np.asarray(landmarks, dtype=np.float64)
    if points.shape != (5, 2) or not np.all(np.isfinite(points)):
        raise ValueError('Expected five finite original-frame landmarks')
    if np.linalg.matrix_rank(points - points.mean(axis=0)) < 2:
        raise ValueError('Degenerate landmarks')
    transform = SimilarityTransform()
    # Keep the upstream float32 target, including its centroid rounding.
    if not transform.estimate(points, ARCFACE_DST):
        raise ValueError('Similarity transform failed')
    forward = transform.params[:2]
    inverse = cv2.invertAffineTransform(forward)
    if abs(np.linalg.det(forward[:, :2])) < 1e-12:
        raise ValueError('Degenerate similarity matrix')
    return dict(content=(112, 112), canvas=(112, 112),
                matrix=inverse_q16(inverse), replicate=False, border=0,
                forward_matrix=forward)
