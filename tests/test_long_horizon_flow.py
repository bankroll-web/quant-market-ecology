import unittest
import numpy as np
import pandas as pd
from long_horizon_flow import features,tokenize,daily
class FlowTests(unittest.TestCase):
 def test_features_prefix_invariant(self):
  n=100;d=pd.DataFrame({5:np.arange(n)+1.,7:(np.arange(n)+1.)*100,8:np.arange(n)+10,9:(np.arange(n)+1.)*.6})
  a=features(d);d.loc[80:,5]=99999;d.loc[80:,9]=20000
  np.testing.assert_allclose(a.iloc[:80],features(d).iloc[:80],equal_nan=True)
 def test_bins_train_only(self):
  x=np.arange(40.).reshape(20,2);a,e=tokenize(x[:10],x);x[10:]=1e9;b,f=tokenize(x[:10],x)
  self.assertEqual(e,f);np.testing.assert_array_equal(a[:10],b[:10])
 def test_costs_and_flat_days(self):
  t=pd.Series(pd.to_datetime(['2024-08-15T00:00Z','2024-08-16T00:00Z']));r=daily(t,np.array([20.,-10.]),np.array([10.,0.]),5,6,6,'2024-08-15','2024-08-17')
  np.testing.assert_allclose(r,[14.,0.,0.])
if __name__=='__main__':unittest.main()
