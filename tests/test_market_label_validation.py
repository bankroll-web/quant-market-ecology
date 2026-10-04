import unittest
from market_label_validation import triple_barrier,purged_walk_forward
class LabelTests(unittest.TestCase):
 def q(self,t,b=100,a=100):return dict(time_ns=t,bid=b,ask=a,segment=1)
 def test_first_touch_wins(self):
  r=triple_barrier([self.q(0),self.q(1,101,101),self.q(2,98,98)],0,3,50,50,max_gap_ns=10)
  self.assertEqual(r['label'],1);self.assertEqual(r['label_available_ns'],1)
 def test_spread_and_fee(self):
  r=triple_barrier([self.q(0,99,100),self.q(1,99,100)],0,1,10,10,roundtrip_fee_bps=2,max_gap_ns=10)
  self.assertEqual(r['label'],-1)
 def test_no_future_coverage_censored(self):
  self.assertEqual(triple_barrier([self.q(0),self.q(1)],0,5,100,100,max_gap_ns=10)['status'],'censored')
 def test_reset_censored(self):
  q=self.q(1);q['segment']=2
  self.assertEqual(triple_barrier([self.q(0),q],0,5,100,100,max_gap_ns=10)['status'],'censored')
 def test_latency_and_asof_exit(self):
  r=triple_barrier([self.q(0),self.q(2),self.q(4),self.q(6)],0,5,100,100,latency_ns=2,max_gap_ns=10)
  self.assertEqual((r['entry_ns'],r['outcome_ns'],r['label_available_ns']),(2,4,6))
 def test_purge_inclusive_overlap_and_future(self):
  e=[dict(start_ns=0,end_ns=4),dict(start_ns=2,end_ns=10),dict(start_ns=10,end_ns=20),dict(start_ns=21,end_ns=22)]
  self.assertEqual(purged_walk_forward(e,[2],embargo_ns=5)[0],[0])
if __name__=='__main__':unittest.main()
