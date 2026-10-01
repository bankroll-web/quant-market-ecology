import unittest
from src.simulation.live_observer import DepthObserver


def snapshot():
    return dict(lastUpdateId=100,bids=[['100','2'],['99','3']],asks=[['101','4'],['102','5']])


def update(first=99,final=101,previous=98,**fields):
    return dict(e='depthUpdate',s='BTCUSDT',U=first,u=final,pu=previous,E=1000,b=[],a=[],**fields)


class LiveObserverTest(unittest.TestCase):
    def test_futures_bridge_is_inclusive_and_snapshot_is_not_yet_valid(self):
        observer=DepthObserver();observer.snapshot(snapshot())
        self.assertFalse(observer.view(1_100_000_000)['usable'])
        observer.update(update(final=100),1_100_000_000)
        self.assertTrue(observer.view(1_100_000_000)['usable'])
        self.assertEqual(observer.sequence,100)

    def test_gap_clears_quotes_and_new_snapshot_recovers(self):
        observer=DepthObserver();observer.snapshot(snapshot())
        observer.update(update(),1_100_000_000)
        observer.update(update(first=102,final=103,previous=999),1_110_000_000)
        self.assertIsNone(observer.view(1_110_000_000)['mid'])
        self.assertEqual(observer.bids,{})
        observer.snapshot(snapshot());observer.update(update(),1_120_000_000)
        self.assertTrue(observer.view(1_120_000_000)['usable'])

    def test_duplicate_does_not_refresh_age_and_silence_hides_prices(self):
        observer=DepthObserver();observer.snapshot(snapshot())
        observer.update(update(),1_100_000_000)
        self.assertFalse(observer.update(update(),1_400_000_000))
        self.assertIsNone(observer.view(1_400_000_000)['mid'])
        self.assertTrue(observer.view(1_400_000_000)['sequence_valid'])

    def test_absolute_quantities_delete_levels_and_reject_crossing(self):
        observer=DepthObserver();observer.snapshot(snapshot())
        event=update();event['b']=[['100','0'],['99','7']]
        observer.update(event,1_100_000_000)
        self.assertEqual(observer.view(1_100_000_000)['bid'],99)
        event=update(first=102,final=102,previous=101);event['b']=[['103','1']]
        observer.update(event,1_150_000_000)
        self.assertFalse(observer.valid)

    def test_disconnect_and_negative_clock_age_hide_every_feature(self):
        observer=DepthObserver();observer.snapshot(snapshot())
        observer.update(update(),900_000_000)
        self.assertIsNone(observer.view(900_000_000)['mid'])
        observer.invalidate('disconnected')
        self.assertIsNone(observer.view(1_000_000_000)['top_obi'])

    def test_snapshot_bridge_gap_and_wrong_symbol(self):
        observer=DepthObserver();observer.snapshot(snapshot())
        wrong=update();wrong['s']='ETHUSDT'
        self.assertFalse(observer.update(wrong,1_100_000_000))
        observer.update(update(first=101,final=103),1_100_000_000)
        self.assertEqual(observer.reason,'snapshot_bridge_gap')
