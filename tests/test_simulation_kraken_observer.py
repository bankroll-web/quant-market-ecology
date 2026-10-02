from decimal import Decimal as D
import unittest
from src.simulation.kraken_observer import KrakenObserver,checksum

class KrakenTests(unittest.TestCase):
    def test_official_crc32_example_preserves_decimal_precision(self):
        bids=[('45283.5','0.10000000'),('45283.4','1.54582015'),('45282.1','0.10000000'),('45281.0','0.10000000'),('45280.3','1.54592586'),('45279.0','0.07990000'),('45277.6','0.03310103'),('45277.5','0.30000000'),('45277.3','1.54602737'),('45276.6','0.15445238')]
        asks=[('45285.2','0.00100000'),('45286.4','1.54571953'),('45286.6','1.54571109'),('45289.6','1.54560911'),('45290.2','0.15890660'),('45291.8','1.54553491'),('45294.7','0.04454749'),('45296.1','0.35380000'),('45297.5','0.09945542'),('45299.5','0.18772827')]
        self.assertEqual(checksum({D(p):D(q) for p,q in bids},{D(p):D(q) for p,q in asks}),3310070434)

    def message(self,kind='snapshot',bids=None,asks=None,crc=None):
        bids=bids if bids is not None else {D('100.0'):D('2.000'),D('99.0'):D('3.000')}
        asks=asks if asks is not None else {D('101.0'):D('4.000'),D('102.0'):D('5.000')}
        return dict(channel='book',type=kind,data=[dict(symbol='BTC/USD',timestamp='1970-01-01T00:00:01Z',checksum=checksum(bids,asks) if crc is None else crc,bids=[dict(price=p,qty=q) for p,q in bids.items()],asks=[dict(price=p,qty=q) for p,q in asks.items()])])

    def test_snapshot_validation_deletion_mismatch_and_recovery(self):
        observer=KrakenObserver()
        self.assertTrue(observer.update_kraken(self.message(),1_100_000_000))
        view=observer.view(1_100_000_000)
        self.assertEqual(view['mid'],100.5)
        self.assertIsNone(view['sequence_valid'])
        self.assertTrue(view['book_validated'])
        message=self.message('update',bids={D('100.0'):D('0')},asks={},crc=checksum({D('99.0'):D('3.000')},observer.asks))
        self.assertTrue(observer.update_kraken(message,1_150_000_000))
        self.assertEqual(observer.view(1_150_000_000)['bid'],99)
        self.assertFalse(observer.update_kraken(self.message('update',crc=1),1_160_000_000))
        self.assertIsNone(observer.view(1_160_000_000)['mid'])
        self.assertTrue(observer.update_kraken(self.message(),1_170_000_000))
        self.assertIsNone(observer.view(3_500_000_000)['mid'])

    def test_depth_truncation_and_missing_timestamp_do_not_invent_age(self):
        observer=KrakenObserver(depth=1)
        message=self.message(crc=checksum({D('100.0'):D('2.000')},{D('101.0'):D('4.000')}))
        del message['data'][0]['timestamp']
        self.assertTrue(observer.update_kraken(message,1_100_000_000))
        self.assertEqual(len(observer.bids),1)
        self.assertIsNone(observer.view(1_100_000_000)['mid'])
        self.assertIsNone(observer.view(1_100_000_000)['receipt_minus_event_ms'])
