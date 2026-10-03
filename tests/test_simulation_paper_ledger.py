import unittest
from src.simulation.paper_ledger import PaperLedger
class PaperLedgerTests(unittest.TestCase):
    def fixture(self,now=0,bid=100,ask=101,estimate=9):
        report=dict(venue='Kraken',symbol='BTC/USD',last_label_ns=now,return_model=dict(center=[0]*5,scale=[1]*5,weights=[estimate,0,0,0,0,0],mse=1,zero_mse=2,evaluation_candidates=30,evaluation_net_mean_bps=1,assumed_roundtrip_cost_bps=6,buffer_bps=2))
        view=dict(research_usable=True,bids=[[bid,1]],asks=[[ask,1]],model_observation=dict(provider='Kraken',symbol='BTC/USD',available_ns=now,event_ns=now,features=[0]*5))
        return report,view
    def test_quote_spread_cost_and_frozen_model(self):
        engine=PaperLedger();report,view=self.fixture();engine.update(report,view,0)
        report['return_model']['weights'][0]=-99
        newer,v=self.fixture(1_000_000_000,102,103)
        result=engine.update(newer,v,1_000_000_000)
        self.assertEqual(engine.model['return_model']['weights'][0],9)
        self.assertEqual(result['paper_trades'],1)
        self.assertAlmostEqual(result['quote_proxy_net_sum_bps'],10000*(102/101-1)-6)
        self.assertFalse(result['orders_enabled'])
    def test_stale_endpoint_invalidates_without_profit(self):
        engine=PaperLedger();engine.update(*self.fixture(),0)
        report,view=self.fixture(1_300_000_000)
        result=engine.update(report,view,1_300_000_000)
        self.assertEqual(result['invalidated_forecasts'],1);self.assertEqual(result['paper_trades'],0)
    def test_wait_still_evaluates_forecast(self):
        engine=PaperLedger();engine.update(*self.fixture(estimate=1),0)
        report,view=self.fixture(1_000_000_000)
        result=engine.update(report,view,1_000_000_000)
        self.assertEqual(result['resolved_forecasts'],1);self.assertEqual(result['paper_trades'],0)
