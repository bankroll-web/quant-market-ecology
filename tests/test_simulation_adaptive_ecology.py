import copy
import unittest
from src.simulation.adaptive_ecology import AdaptiveRates,evaluate
from src.simulation.ecology_calibration import fit,QUANTITIES
from src.simulation.book_change_rates import KINDS

class AdaptiveTests(unittest.TestCase):
    def rows(self):
        return [dict(exposure_seconds=1.,pre_obi_top=0.,pre_bid_depth_10bps=i+1,pre_ask_depth_10bps=i+1,
                     episode=1,received_time_ns=(i+1)*1000000000,**{k:1. for k in KINDS},**{k:2. for k in QUANTITIES}) for i in range(9)]
    def test_update_is_past_only(self):
        a=AdaptiveRates({'x':2.});self.assertEqual(a.rates['x'],2)
        a.update({'x':20},30);self.assertAlmostEqual(a.rates['x'],(2+20/30)/2)
        a.reset();self.assertEqual(a.rates['x'],2)
    def test_current_outcome_cannot_change_current_prediction(self):
        rows=self.rows();m=fit(rows);before=copy.deepcopy(m)
        one=[rows[0]];changed=[{**rows[0],**{k:100 for k in QUANTITIES}}]
        self.assertEqual(evaluate(one,m)['predicted_btc'],evaluate(changed,m)['predicted_btc'])
        self.assertEqual(m,before)
    def test_episode_resets_and_invalid_input(self):
        rows=self.rows();m=fit(rows)
        sample=[rows[0],{**rows[1], 'episode':2}]
        result=evaluate(sample,m);self.assertEqual(result['resets'],2)
        self.assertEqual(result['predicted_btc']['constant'],result['predicted_btc']['adaptive_constant'])
        with self.assertRaises(ValueError):evaluate([rows[1],rows[0]],m)
        with self.assertRaises(ValueError):AdaptiveRates({'x':1},0)
