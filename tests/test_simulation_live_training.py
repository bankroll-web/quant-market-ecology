import unittest
from src.simulation.live_training import LiveTraining
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
