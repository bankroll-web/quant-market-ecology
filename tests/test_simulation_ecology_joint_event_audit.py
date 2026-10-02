import math,unittest
from src.simulation.ecology_joint_event_audit import allocate,receipt_slice
class JointEventTests(unittest.TestCase):
    def test_exact_price_and_side(self):
        r=allocate({('ask',100):5,('bid',99):2},{('ask',100):3,('bid',100):10,('ask',101):4})
        self.assertEqual(r['candidate_execution'],3);self.assertEqual(r['unexplained_reduction'],4);self.assertEqual(r['unmatched_trade'],14)
    def test_cap_prevents_double_removal(self):
        r=allocate({('ask',100):2},{('ask',100):7})
        self.assertEqual(r['candidate_execution'],2);self.assertEqual(r['unexplained_reduction'],0)
        self.assertEqual(r['unmatched_trade'],5)
        self.assertEqual(r['candidate_execution']+r['unexplained_reduction'],r['reduction'])
    def test_missing_trade_is_not_assumed_execution(self):
        self.assertEqual(allocate({('bid',99):4},{})['unexplained_reduction'],4)
    def test_bad_quantities(self):
        for x in (-1,math.nan,math.inf):
            with self.assertRaises(ValueError):allocate({('bid',99):x},{})

    def test_receipt_ties_are_excluded(self):
        times=[10,10,11,15,20,20]
        a,b=receipt_slice(times,10,20)
        self.assertEqual(times[a:b],[11,15])
        with self.assertRaises(ValueError):receipt_slice(times,20,20)
