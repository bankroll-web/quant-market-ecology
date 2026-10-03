import unittest
import numpy as np
from src.simulation.crossasset_daily_data import normalize_ns
from src.simulation.crossasset_daily_research import portfolio,train_indices,fit_model

class DailyResearchTests(unittest.TestCase):
    def test_timestamp_units(self):
        self.assertEqual(normalize_ns(1672531200000),1672531200000000000)
        self.assertEqual(normalize_ns(1735689600000000),1735689600000000000)
    def test_roundtrip_fees_and_hysteresis(self):
        r=portfolio([30,0,-30],[.01,.02,-.5],25)
        self.assertEqual(r['executed_sides'],2)
        self.assertAlmostEqual(r['net_return_pct'],100*((1-.0025)**2*1.01*1.02-1))
        self.assertAlmostEqual(r['long_exposure_fraction'],2/3)
    def test_final_liquidation_fee(self):
        r=portfolio([30],[0],25)
        self.assertEqual(r['executed_sides'],2)
        self.assertAlmostEqual(r['net_return_pct'],100*((1-.0025)**2-1))
    def test_training_labels_resolve_before_observation(self):
        indices=np.arange(7,1000);ns=np.arange(1100,dtype=np.int64)*86400000000000
        tr=train_indices(800,indices,ns)
        self.assertEqual(len(tr),714)
        self.assertEqual(indices[tr[-1]],798)
        self.assertTrue(np.all(ns[indices[tr]+3]<=ns[801]))
        self.assertFalse(np.any(indices[tr]>=799))
    def test_planted_linear_signal(self):
        x=np.linspace(-2,2,200)[:,None];y=100*x[:,0]
        scaler,model=fit_model(x,y,.1)
        p=model.predict(scaler.transform(np.array([[-1.],[1.]])))
        self.assertLess(p[0],-95);self.assertGreater(p[1],95)
    def test_wait_is_cash(self):
        r=portfolio([0,0,0],[1,-.5,2],25)
        self.assertEqual(r['net_return_pct'],0)
        self.assertEqual(r['executed_sides'],0)

if __name__=='__main__':unittest.main()
