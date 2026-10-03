import unittest
from src.simulation.bitcoin_trade_token_audit import flow_interval
class Checks(unittest.TestCase):
    def test_boundaries_and_no_trade_missing(self):
        self.assertEqual(flow_interval([10,20,30],[1,-2,3],10,30),.2);self.assertIsNone(flow_interval([10],[1],10,20))
    def test_gap_and_missing_rejected(self):
        self.assertIsNone(flow_interval([10,20],[1,1],10,20,missing=[15]));self.assertIsNone(flow_interval([10,20],[1,1],10,20,gap_ranges=[(9,16)]))
if __name__=='__main__':unittest.main()
