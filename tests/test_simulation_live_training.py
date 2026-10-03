import unittest
from src.simulation.live_training import LiveTraining,merge_examples
from src.simulation.coinbase_training import train_examples
class LiveTrainingTests(unittest.TestCase):
    def test_background_pipeline_does_not_trade(self):
        engine=LiveTraining()
        try:
            s=engine.status(0);self.assertTrue(s['fitting']);engine.future.result(timeout=10)
            s=engine.status(1);self.assertEqual(s['status'],'insufficient_data');self.assertFalse(s['orders_enabled'])
            engine.record('coinbase_disconnect',{});self.assertEqual(engine.generation,1)
        finally:engine.pool.shutdown(wait=True)
    def test_full_chronological_fit(self):
        rows=[dict(decision_ns=i*2*10**9,target_end_ns=(i*2+1)*10**9,label_available_ns=(i*2+1)*10**9,features=[i%2,0,1,1,0],return_bps=1 if i%2 else -1) for i in range(450)]
        r=train_examples(rows)
        self.assertEqual(r['status'],'offline_development_fit');self.assertFalse(r['qualified'])
        self.assertGreater(r['training_examples'],200);self.assertGreater(r['evaluation_examples'],200)
        rows=[dict(row,return_bps=0) for row in rows]
        self.assertEqual(train_examples(rows)['status'],'insufficient_class_support')
    def test_venue_switch_clears_buffer_and_mixed_training_rejected(self):
        engine=LiveTraining()
        try:
            engine.record('coinbase_model_observation',dict(provider='Coinbase Exchange',symbol='BTC-USD'))
            engine.record('kraken_model_observation',dict(provider='Kraken',symbol='BTC/USD'))
            self.assertEqual(len(engine.records),1);self.assertEqual(engine.records[0]['provider'],'Kraken')
            self.assertEqual(train_examples([dict(provider='Kraken',symbol='BTC/USD'),dict(provider='Coinbase Exchange',symbol='BTC-USD')])['status'],'mixed_venues_rejected')
        finally:engine.pool.shutdown(wait=True)

    def test_audited_retention_deduplicates_shifted_windows(self):
        old=[dict(decision_ns=0),dict(decision_ns=2_000_000_000)]
        new=[dict(decision_ns=100_000_000),dict(decision_ns=2_000_000_000),dict(decision_ns=4_000_000_000)]
        self.assertEqual([r['decision_ns'] for r in merge_examples(old,new)],[0,2_000_000_000,4_000_000_000])
        self.assertEqual(len(merge_examples(old,new,limit=2)),2)
    def test_pending_fit_cannot_cross_returning_venue(self):
        engine=LiveTraining()
        try:
            engine.record('coinbase_model_observation',dict(provider='Coinbase Exchange',symbol='BTC-USD',available_ns=0,event_ns=0,source_update_id=1,features=[0]*5,midpoint=100))
            engine.status(0);engine.future.result(timeout=10)
            engine.record('kraken_model_observation',dict(provider='Kraken',symbol='BTC/USD'))
            engine.record('coinbase_model_observation',dict(provider='Coinbase Exchange',symbol='BTC-USD'))
            self.assertEqual(engine.status(1)['status'],'venue_changed_collecting')
            self.assertEqual(engine.examples,[])
        finally:engine.pool.shutdown(wait=True)
