import unittest
from decimal import Decimal
from src.simulation.coinbase_observer import CoinbaseObserver

class CoinbaseTests(unittest.TestCase):
    def snapshot(self, o):
        return o.update_coinbase(dict(type='snapshot', product_id='BTC-USD', bids=[['100', '2']], asks=[['101', '3']]), 1000000000)
    def update(self, o, changes):
        return o.update_coinbase(dict(type='l2update', product_id='BTC-USD', time='1970-01-01T00:00:01Z', changes=changes), 1100000000)
    def test_absolute_sizes_and_snapshot_clock(self):
        o=CoinbaseObserver();self.assertTrue(self.snapshot(o))
        self.assertFalse(o.view(1000000000)['usable'])
        self.assertTrue(self.update(o, [['buy','100','1']]))
        self.assertEqual(o.bids[Decimal('100')], Decimal('1'))
        self.assertTrue(o.view(1100000000)['usable'])
        self.assertIsNone(o.view(1100000000)['sequence_valid'])
    def test_zero_removal_and_crossed_invalidation(self):
        o=CoinbaseObserver();self.snapshot(o)
        self.assertTrue(self.update(o, [['buy','99','1'],['buy','100','0']]))
        self.assertNotIn(Decimal('100'),o.bids)
        self.assertFalse(self.update(o, [['buy','102','1']]))
        self.assertFalse(o.valid);self.assertEqual(o.bids,{})
        self.assertFalse(self.update(o, [['buy','100','1']]))
    def test_maker_side_inversion_and_gap(self):
        o=CoinbaseObserver();o.observe_match(dict(type='last_match',product_id='BTC-USD',trade_id=10),1)
        self.assertEqual(o.trade_events,0)
        event=dict(type='match',product_id='BTC-USD',trade_id=11,side='sell',size='2')
        o.observe_match(event,2);o.observe_match(event,3)
        self.assertEqual(o.trade_events,1)
        self.assertEqual(o.mechanics.totals['taker_buy_btc'],2)
        event['trade_id']=13
        with self.assertRaises(RuntimeError):o.observe_match(event,4)

    def test_full_book_features_and_reset(self):
        o=CoinbaseObserver()
        o.update_coinbase(dict(type='snapshot',product_id='BTC-USD',bids=[['100','2'],['99.99','4']],asks=[['100.01','3']]),1000000000)
        self.assertIsNone(o.model_observation)
        self.update(o,[['buy','100','1']])
        m=o.view(1100000000)['model_observation']
        self.assertEqual(m['best_quote_ofi_btc'],-1)
        self.assertAlmostEqual(m['depth_btc'],8)
        self.assertAlmostEqual(m['features'][0],-.5)
        self.assertAlmostEqual(m['features'][1],.25)
        self.assertAlmostEqual(m['features'][4],-.125)
        m['features'][0]=99
        self.assertNotEqual(o.model_observation['features'][0],99)
        o.invalidate('reset');self.assertIsNone(o.model_observation)
    def test_depth_cache_reconciles_same_midpoint_updates(self):
        o=CoinbaseObserver()
        o.update_coinbase(dict(type='snapshot',product_id='BTC-USD',bids=[['100','2'],['99.99','4']],asks=[['100.01','3']]),1000000000)
        self.update(o,[['buy','100','1']])
        self.update(o,[['buy','99.99','2'],['sell','100.01','4']])
        self.assertEqual(o.model_observation['depth_btc'],7)
        self.assertAlmostEqual(o.model_observation['features'][1],-1/7)
