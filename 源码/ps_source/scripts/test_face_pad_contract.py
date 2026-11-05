"""PAD contract rejection and ensemble tests; no model/board access."""
import sys
from pathlib import Path
import unittest
import numpy as np
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from model_backend.face_pad import plan_crops, combine_logits, MODELS


class Contract(unittest.TestCase):
    def test_inclusive_full_frame(self):
        for c in plan_crops(100,80,[0,0,100,80]):
            self.assertGreater(c.width,0)
            self.assertLessEqual(c.left+c.width,100)
            self.assertLessEqual(c.top+c.height,80)

    def test_invalid_boxes(self):
        for bbox in ([-1,0,1,1],[0,0,0,1],[0,0,101,1],[0,80,1,1],[0,0,1.5,1],[0,0,True,1],[0,0,np.nan,1]):
            with self.subTest(bbox=bbox),self.assertRaises(ValueError):plan_crops(100,80,bbox)

    def test_invalid_frame_size(self):
        for w,h in ((1,80),(100,0),(8193,80),(True,80)):
            with self.assertRaises(ValueError):plan_crops(w,h,[0,0,1,1])

    def test_both_models_required(self):
        with self.assertRaises(ValueError):combine_logits({MODELS[0][0]:[0,1,2]})
        with self.assertRaises(ValueError):combine_logits({m[0]:[0,np.nan,1] for m in MODELS})

    def test_wrong_logits_shape(self):
        for data in ([0,1],[[0,1,2],[1,2,3]],[0,float('inf'),1]):
            with self.assertRaises(ValueError):combine_logits({m[0]:data for m in MODELS})

    def test_stable_softmax_and_mean(self):
        result=combine_logits({m[0]:[1000,1001,1000] for m in MODELS})
        self.assertTrue(result['model_predicts_live'])
        self.assertAlmostEqual(sum(result['scores']),1)
        self.assertFalse(result['calibrated'])
        self.assertAlmostEqual(result['live_score'],np.e/(np.e+2))

    def test_each_model_softmax_before_mean(self):
        result=combine_logits({MODELS[0][0]:[0,4,0],MODELS[1][0]:[0,0,2]})
        p=np.exp([0,4,0]);p/=p.sum()
        q=np.exp([0,0,2]);q/=q.sum()
        np.testing.assert_allclose(result['scores'],(p+q)/2)


if __name__=='__main__':unittest.main()
