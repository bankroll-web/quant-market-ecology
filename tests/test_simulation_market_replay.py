"""Replay observer: preserve missing states, receipt boundaries and exposure."""
import unittest
import tempfile
from pathlib import Path

from src.simulation.market_replay import build_seconds, render


def state(received, exposure, mid):
    row = dict(received_time_ns=received, event_time_ms=(received-100_000_000)//1_000_000,
               exposure_seconds=exposure, episode=1, post_best_bid=mid-.05,
               post_best_ask=mid+.05, post_mid=mid, post_bid_depth_10bps=10,
               post_ask_depth_10bps=20, post_obi_top=.1)
    row.update({s+'_'+k+'_qty': 0 for s in ('bid','ask') for k in ('add','remove')})
    return row


class MarketReplayTest(unittest.TestCase):
    def test_exposure_splits_across_seconds_and_prices_are_not_carried(self):
        rows = [state(900_000_000,.2,100), state(1_100_000_000,.2,101)]
        result = build_seconds(rows, [(999_000_000,2.,100.),(1_000_000_000,-3.,500.)],0,count=3)
        self.assertAlmostEqual(result[0]['verified_exposure_seconds'],.3)
        self.assertAlmostEqual(result[1]['verified_exposure_seconds'],.1)
        self.assertEqual(result[0]['net_btc'],2.)
        self.assertEqual(result[1]['net_btc'],-3.)
        self.assertTrue(result[0]['fresh_messages'])
        self.assertFalse(result[1]['fresh_messages'])
        self.assertIsNone(result[2]['book'])

    def test_overlapping_exposure_is_rejected(self):
        with self.assertRaises(ValueError):
            build_seconds([state(900_000_000,.9,100),state(950_000_000,.9,100)],[],0,count=2)

    def test_charts_exist_in_initial_markup_without_javascript(self):
        rows = build_seconds([state(900_000_000,.2,100)],[],0,count=3)
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)/'replay.html'
            render({'2026-05-25_12':rows},path)
            markup = path.read_text().split('<script>')[0]
            self.assertIn('id="static-preview"',markup)
            self.assertEqual(markup.count('<svg '),3)
            self.assertIn('Minute within UTC hour',markup)
            self.assertIn('id="interactive-plots" class="panel" hidden',markup)


if __name__ == '__main__':
    unittest.main()
