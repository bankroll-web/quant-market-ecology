import csv
import math
from pathlib import Path
import tempfile
import unittest
from src.simulation.history_strategy import history_map,augment

class HistoryTests(unittest.TestCase):
    def write(self,path,rows):
        with path.open('w') as f:
            w=csv.DictWriter(f,fieldnames=rows[0]);w.writeheader();w.writerows(rows)
    def rows(self):
        return [dict(start_received_ns=i*1000000000,end_received_ns=(i+1)*1000000000,episode=1,signed_btc=i+1,absolute_trade_btc=i+2,mid_log_return_bps=i,forward_5s_return_bps=1000) for i in range(3)]
    def test_future_and_current_outcomes_not_in_lags(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'flow.csv';rows=self.rows();self.write(p,rows);before=history_map(p)
            rows[2]['signed_btc']=999;rows[0]['forward_5s_return_bps']=-999;self.write(p,rows)
            after=history_map(p);self.assertEqual(before[3000000000],after[3000000000])
            self.assertEqual(len(after[3000000000]),2)
            x=augment([dict(decision_ns=3000000000,x=[0,0,0,0,0,math.log1p(10)])],after)[0]['x']
            self.assertAlmostEqual(x[6],.2);self.assertEqual(x[9],1.)
    def test_gap_and_episode_reset(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'flow.csv';rows=self.rows();rows[1]['episode']=2;rows[2]['episode']=2;rows[2]['start_received_ns']+=10000
            self.write(p,rows);h=history_map(p)
            self.assertEqual(h[2000000000],[]);self.assertEqual(h[3000000000],[])
    def test_unordered_windows_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'flow.csv';self.write(p,list(reversed(self.rows())))
            with self.assertRaises(ValueError):history_map(p)
