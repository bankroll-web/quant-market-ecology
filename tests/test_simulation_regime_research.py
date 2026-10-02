import unittest
import numpy as np
from src.simulation.regime_research import thresholds,signals,evaluate,block_interval

class RegimeResearchTests(unittest.TestCase):
    def test_training_quantiles_are_not_recomputed_on_future_regimes(self):
        rows=[dict(x=[i/100,i/10,1,0,.1,i]) for i in range(10)]
        cuts=thresholds(rows)
        unknown=[dict(x=[.01,.1,1,0,.1,1e9])]
        np.testing.assert_array_equal(signals('flow_follow:thin',unknown,cuts,{}),[0])
        np.testing.assert_array_equal(signals('flow_follow:deep',unknown,cuts,{}),[1])
        np.testing.assert_array_equal(signals('flow_reverse:deep',unknown,cuts,{}),[-1])
        self.assertLess(cuts['depth_high'],10)

    def test_missing_exit_stress_counts_only_attempted_positions(self):
        rows=[dict(long_quote_bps=10,short_quote_bps=-10)]
        unresolved=[dict(x=[0]*6),dict(x=[0]*6)]
        score=evaluate(rows,unresolved,[1],[0,-1],5.)
        self.assertEqual(score['summed_net_bps'],5)
        self.assertEqual(score['unresolved_opened_trades'],1)
        self.assertEqual(score['stress_50bps_sum'],-45)
        self.assertEqual(evaluate(rows,unresolved,[0],[0,0],5.)['stress_50bps_sum'],0)

    def test_block_interval_retains_zero_trade_opportunities(self):
        rows=[dict(decision_ns=i*60_000_000_000,long_quote_bps=10,short_quote_bps=-10) for i in range(12)]
        r=block_interval(rows,[0]*12)
        self.assertEqual(r['blocks'],12);self.assertEqual(r['lower'],0);self.assertEqual(r['upper'],0)
        self.assertIsNone(block_interval(rows[:2],[1,1])['lower'])
