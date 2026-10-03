import tempfile
import unittest
from pathlib import Path
from src.simulation.river_live import RiverLive, VERSION


def obs(ns,mid=100.):
    return dict(provider='Coinbase Exchange',symbol='BTC-USD',event_ns=ns-10_000_000,
        midpoint=mid,features=[.1,.2,2.,.1,.05],depth_btc=10.,
        trade_subscription_active=True,liquidity_changes={'bid_added_btc':1.})


class Tests(unittest.TestCase):
    def warm(self,m):
        start=1_000_000_000_000
        for i in range(16):m.observe(obs(start+i*100_000_000),start+i*100_000_000)
        return start+1_500_000_000

    def test_delayed_score_before_learning_and_gap_reset(self):
        m=RiverLive();decision=self.warm(m)
        self.assertEqual(m.updates,0);self.assertEqual(m.decisions,1)
        self.assertEqual(m.pending[0]['forecast_bps'],0)
        for i in range(1,300):
            t=decision+i*100_000_000;m.observe(obs(t,101),t)
        self.assertEqual(m.updates,0)
        t=decision+30_000_000_000;m.observe(obs(t,101),t)
        self.assertEqual(m.updates,1)
        self.assertAlmostEqual(m.loss,10000.)
        self.assertAlmostEqual(m.loss,m.zero_loss)
        m.observe(obs(t+3_000_000_000),t+3_000_000_000)
        self.assertEqual(len(m.pending),0)
        self.assertGreater(m.dropped,0)

    def test_timing_venue_trade_gate(self):
        m=RiverLive();t=self.warm(m)
        m.record('coinbase_verified_match',{'qty':2.,'side':'buy'},t+1)
        m.observe(obs(t+100_000_000),t+100_000_000)
        self.assertEqual(m.latest['values']['signed_flow_btc'],2)
        bad=obs(t+200_000_000);bad['event_ns']=t-1_000_000_000
        m.observe(bad,t+200_000_000)
        self.assertEqual(len(m.context),0)
        self.assertEqual(len(m.pending),0)
        bad=obs(t+300_000_000);bad['trade_subscription_active']=False
        m.observe(bad,t+300_000_000);self.assertEqual(len(m.context),0)
        bad=obs(t+400_000_000);bad['symbol']='BTC-USDT'
        m.observe(bad,t+400_000_000);self.assertEqual(len(m.context),0)

    def test_checkpoint_restore_prediction_and_no_pending_labels(self):
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'checkpoint.json';m=RiverLive(path);t=self.warm(m)
            for i in range(1,310):
                ns=t+i*100_000_000;m.observe(obs(ns,100+i/10000),ns)
            x=m.pending[-1]['x'];forecast=m.model.predict_one(x)
            m.view(ns,{'provider':'Coinbase Exchange','symbol':'BTC-USD'},True,True)
            restored=RiverLive(path)
            self.assertTrue(restored.restored)
            self.assertAlmostEqual(forecast,restored.model.predict_one(x),places=12)
            self.assertEqual(restored.updates,m.updates)
            self.assertFalse(restored.pending)
            self.assertFalse(restored.context)
            self.assertEqual(restored.snapshot()['version'],VERSION)


if __name__=='__main__':unittest.main()
