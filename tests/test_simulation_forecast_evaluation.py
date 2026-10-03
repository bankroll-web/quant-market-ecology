import unittest,math
from src.simulation.forecast_evaluation import gate_inputs,gate_training,score,skill
class ForecastEvaluationTests(unittest.TestCase):
    def test_release_time_blocks_late_input(self):
        with self.assertRaises(ValueError):gate_inputs(100,[dict(event_ns=50,available_ns=101)])
        self.assertTrue(gate_inputs(100,[dict(event_ns=50,available_ns=100)]))
    def test_training_labels_must_be_resolved(self):
        with self.assertRaises(ValueError):gate_training(100,[dict(target_end_ns=90,label_available_ns=101)])
        self.assertTrue(gate_training(100,[dict(target_end_ns=90,label_available_ns=100)]))
    def test_scores_and_zero_class(self):
        r=score([1,0,.5],[1,0,-3],[(0,2),(-1,1),(-1,1)])
        self.assertAlmostEqual(r['brier'],.25/3)
        self.assertAlmostEqual(r['winkler'],26/3)
        self.assertAlmostEqual(r['interval_coverage'],2/3)
        self.assertIsNone(skill(0,0));self.assertEqual(skill(.1,.2),.5)
    def test_invalid_values(self):
        for p in (math.nan,1.1,-.1):
            with self.assertRaises(ValueError):score([p],[0],[(-1,1)])
        with self.assertRaises(ValueError):score([],[],[])
