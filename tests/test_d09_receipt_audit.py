import unittest
import numpy as np
from audit_d09_receipts import interval_receipts
class Checks(unittest.TestCase):
    def test_right_right_and_max_receipt(self):
        count,last,*_=interval_receipts(np.array([10,20,20,30]),np.array([100,250,200,300]),[10,20],[20,30]);self.assertEqual(count.tolist(),[2,1]);self.assertEqual(last.tolist(),[250,300])
    def test_no_trade_provenance_missing(self):
        count,last,*_=interval_receipts(np.array([10]),np.array([100]),[10],[20]);self.assertEqual(last.tolist(),[0]);self.assertEqual(count.tolist(),[0])
if __name__=='__main__':unittest.main()
