import unittest
from src.simulation.observed_ecology_environment import examples,ObservedEnvironment,FEATURES
class EnvironmentTests(unittest.TestCase):
    def rows(self):
        return [dict(received_time_ns=i*100000000,event_time_ms=i*100,episode=1,**{k:(101 if k=='post_best_ask' else 99 if k=='post_best_bid' else 100 if k=='post_mid' else 1) for k in FEATURES}) for i in range(25)]
    def test_observation_hides_labels(self):
        data=examples(self.rows());env=ObservedEnvironment(data)
        obs=env.step();self.assertNotIn('label',obs)
        obs['observation']['post_mid']=0;self.assertEqual(data[0]['observation']['post_mid'],100)
        env.reset();self.assertEqual(env.step()['decision_ns'],0)
    def test_gaps_remove_target(self):
        rows=self.rows();rows[5]['episode']=2
        data=examples(rows);self.assertNotIn(0,[r['decision_ns'] for r in data])
    def test_future_event_rejected(self):
        rows=self.rows();rows[0]['event_time_ms']=1
        with self.assertRaises(ValueError):examples(rows)
