import unittest
import numpy as np
from src.simulation.six_field_tokens import QuantileCodec,SixFieldTokenizer,SummaryTokenizer
class Checks(unittest.TestCase):
    def setUp(self):self.c=QuantileCodec().fit(np.arange(100)/100,np.arange(100),100)
    def test_future_and_rolling(self):
        with self.assertRaises(ValueError):QuantileCodec().fit([1,2],[10,20],15)
        c=QuantileCodec().fit([1,2,3],[10,20,30],30,15);self.assertEqual(c.lower,2)
    def test_missing_and_outside(self):
        t=self.c.encode([-1,np.nan,10]);self.assertEqual(t.tolist(),[0,34,33]);self.assertTrue(np.isnan(self.c.decode(t)[1]))
    def test_six_disjoint_fields(self):
        m=SixFieldTokenizer(self.c,self.c);t=m.encode('trade','buy',-2,1,.1,decision_ns=101);self.assertEqual(len(t),6);self.assertEqual(len(set(t)),6);self.assertTrue(max(t)<m.vocabulary_size)
        with self.assertRaises(ValueError):m.encode('trade','buy',2,1,.1,decision_ns=99)
    def test_participant_future(self):
        with self.assertRaises(ValueError):SixFieldTokenizer(self.c,self.c).encode('trade','buy',2,1,.1,participant=1,decision_ns=101,cluster_fit_ns=102)
    def test_summary_availability_and_missing(self):
        m=SummaryTokenizer({f:self.c for f in SummaryTokenizer.fields})
        self.assertEqual(len(m.encode({},90,95,101)),6)
        with self.assertRaises(ValueError):m.encode({},102,103,101)
    def test_identity_frequency(self):self.assertAlmostEqual(self.c.audit(np.arange(100)/100,np.arange(100)/100)['frequency_js_divergence'],0)
if __name__=='__main__':unittest.main()
