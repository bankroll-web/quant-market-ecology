import unittest
import numpy as np
import pandas as pd
from flow_activity_hypothesis import causal_features,interval
class ActivityTests(unittest.TestCase):
 def test_future_cannot_change_past_features(self):
  n=1600;d=pd.DataFrame({5:np.ones(n)*10,9:np.ones(n)*6,8:np.arange(n)+100.});a=causal_features(d);d.loc[1500:,8]=1e8;d.loc[1500:,9]=10
  np.testing.assert_allclose(a.iloc[:1500],causal_features(d).iloc[:1500],equal_nan=True)
 def test_reference_excludes_current_count(self):
  n=1500;d=pd.DataFrame({5:np.ones(n)*10,9:np.ones(n)*6,8:np.ones(n)*100});d.loc[1440,8]=1600
  self.assertAlmostEqual(causal_features(d).activity_ratio.iloc[1440],2.)
 def test_no_uncertainty_from_one_day(self):self.assertIsNone(interval([3],np.random.default_rng(1)))
if __name__=='__main__':unittest.main()
