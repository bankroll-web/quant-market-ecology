import unittest
import numpy as np
from src.simulation.robust_paper_benchmark import fit,predict
class RobustPaperTests(unittest.TestCase):
    def test_constant_features_with_extreme_target(self):
        x=np.zeros((100,5));y=np.zeros(100);y[-1]=10000
        m=fit(x,y);p,_=predict(x,m)
        self.assertTrue(np.isfinite(p).all());self.assertLess(abs(p[0]),.01)
    def test_planted_relationship_positive_control(self):
        rng=np.random.default_rng(8);x=rng.uniform(-1,1,(1000,5));y=2*x[:,0]+rng.normal(0,.1,1000)
        m=fit(x[:700],y[:700]);p,_=predict(x[700:],m)
        self.assertLess(np.mean((p-y[700:])**2),np.mean(y[700:]**2)*.2)
    def test_extreme_features_are_reported_and_bounded(self):
        rng=np.random.default_rng(9);x=rng.uniform(-1,1,(100,5));m=fit(x,x[:,0])
        p,flag=predict(np.full((1,5),1e100),m)
        self.assertTrue(flag[0]);self.assertTrue(np.isfinite(p[0]))
