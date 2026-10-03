import unittest
from decimal import Decimal as D
from src.simulation.market_mechanics import MarketMechanics
from src.simulation.kraken_observer import KrakenObserver,checksum

class MarketMechanicsTests(unittest.TestCase):
    def test_rolling_window_excludes_old_data_and_deduplicates_trades(self):
        m=MarketMechanics();m.record(1_000_000_000,{'ask_added_btc':2},100)
        trade=dict(trade_id=1,qty=3,side='buy')
        self.assertTrue(m.trade(trade,2_000_000_000));self.assertFalse(m.trade(trade,3_000_000_000))
        m.record(11_000_000_000,{'ask_removed_btc':1},101)
        v=m.view(11_000_000_000,True,True)
        self.assertEqual(v['status'],'observed');self.assertEqual(v['taker_buy_btc'],3)
        self.assertEqual(v['ask_add_remove_ratio'],2)
        self.assertAlmostEqual(v['observed_midpoint_move_bps'],100)
        v=m.view(13_000_000_000,True,True)
        self.assertEqual(v['taker_buy_btc'],0);self.assertEqual(v['ask_added_btc'],0)
        self.assertIsNone(v['observed_midpoint_move_bps'])

    def test_reset_invalid_trade_and_bounded_capacity(self):
        m=MarketMechanics(max_events=2)
        m.record(1,{'bid_added_btc':1},100);m.record(2);m.record(3)
        self.assertEqual(m.view(10_000_000_001,True,True)['status'],'warming_or_incomplete')
        self.assertFalse(m.trade(dict(trade_id=5,qty=-1,side='buy'),10_000_000_002))
        self.assertGreater(m.view(10_000_000_003,True,True)['excluded_trade_events'],0)
        m.reset();self.assertEqual(m.view(20_000_000_000,False,True)['status'],'unavailable')
        self.assertEqual(m.totals['bid_added_btc'],0)

    def test_crc32_failure_does_not_record_book_changes(self):
        o=KrakenObserver();o.trade_subscribed=True
        bids={D('100'):D('2')};asks={D('100.1'):D('2')}
        def msg(kind,bidq,crc):
            return dict(channel='book',type=kind,data=[dict(symbol='BTC/USD',timestamp='2026-10-02T00:00:00Z',bids=[dict(price='100',qty=str(bidq))],asks=[dict(price='100.1',qty='2')],checksum=crc)])
        self.assertTrue(o.update_kraken(msg('snapshot',2,checksum(bids,asks)),1))
        self.assertEqual(o.mechanics.totals['bid_added_btc'],0)
        bids[D('100')]=D('3')
        self.assertTrue(o.update_kraken(msg('update',3,checksum(bids,asks)),2))
        self.assertEqual(o.mechanics.totals['bid_added_btc'],1)
        self.assertFalse(o.update_kraken(msg('update',10,0),3))
        self.assertEqual(o.mechanics.totals['bid_added_btc'],0)
        self.assertFalse(o.valid)
