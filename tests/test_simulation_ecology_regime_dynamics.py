import unittest
import numpy as np
from src.simulation.ecology_regime_dynamics import state,summarize,fit


class RegimeDynamicsTests(unittest.TestCase):
    def row(self,start,end,episode=1,sign=1,pressure=.2,display=.1):
        return dict(start_ns=start,end_ns=end,episode=episode,signed_btc=sign,trade_pressure=pressure,display_pressure=display,duration_seconds=(end-start)/1e9,move_bps=0)
    def test_relative_sign_classification(self):
        self.assertEqual(state(self.row(0,1,sign=-1,display=-1),.1),'high_reinforces')
        self.assertEqual(state(self.row(0,1,sign=-1,display=1),.1),'high_opposes')
        self.assertEqual(state(self.row(0,1,sign=0),.1),'no_signed_flow')
    def test_transitions_do_not_bridge_gap_or_episode(self):
        rows=[self.row(0,100),self.row(100,200),self.row(300,400),self.row(400,500,episode=2)]
        s,p,_=summarize(rows,.1)
        self.assertEqual(p,[(0,1)]);self.assertEqual(s['excluded_boundaries'],2)
        self.assertEqual(s['regimes']['high_reinforces']['completed_runs'],0)
    def test_completed_run_excludes_boundary_censoring(self):
        rows=[self.row(0,100,pressure=0),self.row(100,200),self.row(200,300),self.row(300,400,pressure=0)]
        s,_,_=summarize(rows,.1);r=s['regimes']['high_reinforces']
        self.assertEqual(r['completed_runs'],1);self.assertEqual(r['boundary_censored_runs'],0)
    def test_smoothed_rows_normalize_even_without_observed_source_state(self):
        model=fit([[0]*5 for _ in range(5)])
        np.testing.assert_allclose(np.sum(model['markov'],axis=1),1)
        self.assertAlmostEqual(sum(model['iid']),1)
