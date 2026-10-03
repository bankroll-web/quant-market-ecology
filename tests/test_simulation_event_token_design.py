import unittest
from dataclasses import replace
from src.simulation.event_token_design import Event,fit,encode,available_scales,promotion_gate
class EventDesignChecks(unittest.TestCase):
    def setUp(self):
        self.events=[Event(i,i,'trade','buy',101+i,100+i,1+i,i,'a') for i in range(1,20)]
    def test_future_fit_rejected(self):
        with self.assertRaises(ValueError):fit(self.events,10)
    def test_scale_invariance_and_missing_gap(self):
        m=fit(self.events,20);a=self.events[-1];b=replace(a,price=a.price*100,reference_mid=a.reference_mid*100)
        self.assertEqual(encode(a,m),encode(b,m));self.assertIn('log_gap_seconds:missing',encode(a,m))
    def test_future_reference_and_cluster_rejected(self):
        m=fit(self.events,20)
        for a in (replace(self.events[-1],reference_available_ns=99),replace(self.events[-1],participant_cluster='0')):
            with self.assertRaises(ValueError):encode(a,m)
    def test_episode_and_order_boundaries(self):
        m=fit(self.events,20)
        with self.assertRaises(ValueError):encode(replace(self.events[-1],episode='b'),m,self.events[-2])
        with self.assertRaises(ValueError):encode(self.events[-2],m,self.events[-1])
    def test_multiscale_receipt_gate(self):
        frames=[dict(scale='minute',period_end_ns=60,available_ns=65),dict(scale='minute',period_end_ns=120,available_ns=125)]
        self.assertEqual(available_scales(100,frames)['minute']['period_end_ns'],60)
        self.assertEqual(available_scales(64,frames),{})
    def test_no_evidence_no_promotion(self):
        self.assertFalse(promotion_gate({})['qualified']);self.assertFalse(promotion_gate({})['orders_enabled'])
if __name__=='__main__':unittest.main()
