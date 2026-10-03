import unittest
from src.simulation.paper_signal import assess
class PaperSignalTests(unittest.TestCase):
    def inputs(self,estimate):
        report=dict(venue='Kraken',symbol='BTC/USD',last_label_ns=100,return_model=dict(center=[0]*5,scale=[1]*5,feature_lower=[-1]*5,feature_upper=[1]*5,weights=[estimate,0,0,0,0,0],mse=1,zero_mse=2,evaluation_candidates=30,evaluation_net_mean_bps=1,assumed_roundtrip_cost_bps=6,buffer_bps=2))
        view=dict(research_usable=True,model_observation=dict(provider='Kraken',symbol='BTC/USD',available_ns=100,event_ns=100,features=[0]*5))
        return report,view
    def test_paper_directions_without_order_authorization(self):
        for value,expected in [(9,'BUY'),(-9,'SELL'),(1,'WAIT')]:
            r=assess(*self.inputs(value),100);self.assertEqual(r['signal'],expected);self.assertFalse(r['orders_enabled']);self.assertFalse(r['qualified'])
    def test_stale_and_wrong_venue_rejected(self):
        r,v=self.inputs(9);v['model_observation']['provider']='Coinbase Exchange'
        self.assertEqual(assess(r,v,100)['signal'],'WAIT')
        self.assertEqual(assess(*self.inputs(9),1_000_000_000)['signal'],'WAIT')
    def test_failed_development_cost_gate_rejected(self):
        r,v=self.inputs(9);r['return_model']['evaluation_candidates']=0
        self.assertEqual(assess(r,v,100)['signal'],'WAIT')

    def test_extrapolated_state_cannot_signal(self):
        r,v=self.inputs(9);v['model_observation']['features'][4]=100
        result=assess(r,v,100)
        self.assertEqual(result['signal'],'WAIT')
        self.assertTrue(any('extrapolation' in reason for reason in result['reasons']))
