import unittest
from types import SimpleNamespace
from collections import deque
from src.simulation.research_checkpoint import snapshot,restore
class CheckpointTests(unittest.TestCase):
    def objects(self):
        t=SimpleNamespace(venue=('Kraken','BTC/USD'),examples=[dict(provider='Kraken',symbol='BTC/USD',decision_ns=1,target_end_ns=2,label_available_ns=2,features=[0]*5,return_bps=0)],report={'qualified':False},generation=0,records=deque([1]))
        l=SimpleNamespace(model={'qualified':False},frozen_ns=1,model_id='abc',resolved=1,invalid=0,trades=0,net_sum=0.,loss_sum=0.,zero_loss_sum=0.,complete=False,rows=deque(maxlen=20),pending={'decision_ns':1})
        return t,l
    def test_restore_keeps_labels_but_never_bridges_outage(self):
        t,l=self.objects();s=snapshot(t,l);t.examples=[]
        restore(s,t,l)
        self.assertEqual(len(t.examples),1);self.assertEqual(len(t.records),0)
        self.assertIsNone(l.pending);self.assertTrue(l.complete);self.assertEqual(l.invalid,1)
    def test_invalid_timing_rejected_before_mutation(self):
        t,l=self.objects();s=snapshot(t,l);s['training']['examples'][0]['label_available_ns']=0
        with self.assertRaises(ValueError):restore(s,t,l)
        self.assertEqual(len(t.records),1)
    def test_nonfinite_checkpoint_rejected(self):
        t,l=self.objects();t.examples[0]['return_bps']=float('nan')
        with self.assertRaises(ValueError):snapshot(t,l)
