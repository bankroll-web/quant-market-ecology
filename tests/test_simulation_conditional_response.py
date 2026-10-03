import unittest
import numpy as np
import pandas as pd
from src.simulation.ecology_conditional_response import response,design,clustered_interval
class ConditionalResponseTests(unittest.TestCase):
    def test_forward_target_and_endpoint(self):
        a=pd.DataFrame(dict(close=[100,101,102,103],bucket=np.arange(4)*300000))
        y,end=response(a,3)
        self.assertAlmostEqual(y.iloc[0],10000*np.log(1.03))
        self.assertEqual(end.iloc[0],1200000)
        self.assertTrue(np.isnan(y.iloc[1]))
    def test_daily_cluster_interval_and_small_sample(self):
        a=pd.DataFrame(dict(date=['a','a','b'],value=[2,2,2]))
        self.assertEqual(clustered_interval(a,'value',1),[2.,2.])
        self.assertIsNone(clustered_interval(a[a.date=='b'],'value',1))
