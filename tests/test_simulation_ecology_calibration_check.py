import json
from pathlib import Path
import unittest
from src.simulation.ecology import run,common_flow
from src.simulation.ecology_calibration_check import ObservedBook,compare


class CalibrationCheckTests(unittest.TestCase):
    def setUp(self):
        self.params=json.loads((Path(__file__).resolve().parents[1]/'configs/simulation_v1_demo.json').read_text())['calibration_from_valid_samples']
    def test_instrumentation_preserves_original_simulation(self):
        flow=common_flow(self.params,7)
        original,original_shock=run(self.params,flow,False)
        observed,observed_shock=run(self.params,flow,False,book_factory=ObservedBook)
        self.assertEqual(original_shock,observed_shock)
        for a,b in zip(original,observed):
            for key,value in a.items():self.assertEqual(value,b[key])
    def test_trade_observation_uses_filled_quantity_and_side(self):
        book=ObservedBook(self.params);book.begin_observation(0)
        filled,_=book.execute('buy',.1)
        self.assertAlmostEqual(book.observed['buy'],filled)
        self.assertAlmostEqual(book.observed['ask_remove'],filled)
        self.assertEqual(book.observed['bid_remove'],0)
        self.assertGreater(book.state(0,'test')['display_pressure'],0)
    def test_zero_distance_for_identical_empirical_summaries(self):
        from src.simulation.ecology_regime_dynamics import STATES
        summary=dict(windows=5,regimes={s:dict(windows=1,median_observed_run_seconds=1.) for s in STATES},transition_counts=[[1]*5 for _ in STATES])
        result=compare(summary,summary)
        self.assertEqual(result['occupancy_total_variation'],0)
        self.assertTrue(all(v==0 for v in result['transition_row_total_variation'].values()))
