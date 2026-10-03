import unittest
from src.simulation.live_model_status import assess
from src.simulation.frozen_probability_model import ARTIFACT
class LiveModelTests(unittest.TestCase):
    def test_cross_venue_abstains(self):
        r=assess(dict(provider='Coinbase Exchange',symbol='BTC-USD'),dict(research_usable=True),100)
        self.assertEqual(r['signal'],'WAIT');self.assertIsNone(r['positive_return_probability']);self.assertFalse(r['orders_enabled'])
    def test_fresh_matching_features_still_unqualified(self):
        r=assess(dict(provider='Binance Futures',symbol='BTCUSDT'),dict(research_usable=True,model_observation=dict(available_ns=100,features=ARTIFACT['model']['center'])),100)
        self.assertEqual(r['signal'],'WAIT');self.assertIsNotNone(r['positive_return_probability'])
    def test_future_features_rejected(self):
        r=assess(dict(provider='Binance Futures',symbol='BTCUSDT'),dict(research_usable=True,model_observation=dict(available_ns=101,features=ARTIFACT['model']['center'])),100)
        self.assertIsNone(r['positive_return_probability'])
