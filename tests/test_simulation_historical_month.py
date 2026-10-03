import tempfile,unittest,zipfile
from pathlib import Path
import numpy as np
import pandas as pd
from src.simulation.historical_month_research import aggregate,ridge,predict,metrics
class MonthResearchTests(unittest.TestCase):
    def test_side_features_and_future_execution(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'x.zip'
            with zipfile.ZipFile(p,'w') as z:
                z.writestr('x.csv','id,price,qty,first,last,time,maker\n1,100,2,1,1,0,false\n2,101,1,2,2,1,true\n3,102,1,3,3,300000,false\n4,103,1,4,4,300001,false\n5,104,1,5,5,600000,true\n')
            a,audit=aggregate(p)
            self.assertAlmostEqual(a.imbalance.iloc[0],1/3)
            self.assertAlmostEqual(a.target_bps.iloc[0],10000*(103/102-1))
            self.assertTrue((a.entry_time>=a.decision_time).all())
            self.assertEqual(audit['aggregate_id_gaps'],0)
    def test_fixed_ridge_finite_on_constant_features(self):
        x=np.ones((20,5));m=ridge(x,np.arange(20))
        self.assertTrue(np.isfinite(predict(x,m)).all())
    def test_duplicate_ids_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'x.zip'
            with zipfile.ZipFile(p,'w') as z:z.writestr('x.csv','id,price,qty,first,last,time,maker\n1,100,1,1,1,0,false\n1,101,1,2,2,300000,true\n')
            with self.assertRaises(ValueError):aggregate(p)

    def test_cost_sensitivity_preserves_entry_decision(self):
        a=pd.DataFrame(dict(target_bps=[10.],date=['2026-09-26']))
        self.assertEqual(metrics(a,np.array([7.]),0,cost=12)['trades'],1)
        self.assertEqual(metrics(a,np.array([7.]),0,cost=12)['sum_trade_return_bps'],-2)
