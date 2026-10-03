import unittest
import numpy as np
from src.simulation.ecology_probability_model import fit,predict
class ProbabilityModelTests(unittest.TestCase):
    def test_constant_feature_matches_base_rate(self):
        x=np.ones((10,2));y=np.array([1,1]+[0]*8)
        m=fit(x,y);self.assertTrue(np.allclose(predict(x,m),.2,atol=1e-8))
    def test_signal_and_immutable_transform(self):
        x=np.array([[-2.],[-1.],[1.],[2.]]);m=fit(x,np.array([0,0,1,1]));before=dict(m)
        p=predict(np.array([[-10.],[10.]]),m)
        self.assertLess(p[0],p[1]);self.assertEqual(m,before)
        self.assertTrue(np.isfinite(p).all())
