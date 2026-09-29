"""Check sign preservation, receipt-time boundaries and valid-episode horizons."""
import csv
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from src.simulation.flow_response import NS, summarize, windows


class FlowResponseTest(unittest.TestCase):
    def test_alignment_preserves_price_direction(self):
        rows = [dict(signed_btc=2., absolute_trade_btc=2., mid_log_return_bps=-3.),
                dict(signed_btc=-2., absolute_trade_btc=2., mid_log_return_bps=-1.)]
        self.assertEqual(summarize(rows, 1.)['mean_direction_aligned_return_bps'], -1.)

    def test_boundary_trades_count_once_and_horizons_do_not_cross_episode(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'changes.csv'
            rows = [dict(received_time_ns=i * NS, episode=1, pre_mid=100 + i)
                    for i in range(8)]
            rows.extend([dict(received_time_ns=20 * NS, episode=2, pre_mid=200),
                         dict(received_time_ns=21 * NS, episode=2, pre_mid=201)])
            with path.open('w', newline='') as handle:
                writer = csv.DictWriter(handle, fieldnames=rows[0])
                writer.writeheader(); writer.writerows(rows)
            # A trade exactly at a right boundary belongs to the next window.
            with patch('src.simulation.flow_response.trade_tape', return_value=[
                    (NS // 2, 2., 100.), (NS, -3., 100.), (9 * NS, 99., 100.), (20 * NS, 4., 100.)]):
                result = windows(path, 'unused')
            self.assertEqual([r['signed_btc'] for r in result[:2]], [2., -3.])
            self.assertEqual(sum(r['absolute_trade_btc'] for r in result), 9.)
            self.assertIsNotNone(result[0]['forward_5s_return_bps'])
            self.assertIsNone(result[6]['forward_1s_return_bps'])
            self.assertEqual(result[-1]['episode'], '2')

    def test_delayed_trade_rejects_window_instead_of_silently_reducing_flow(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'changes.csv'
            with path.open('w', newline='') as handle:
                writer = csv.DictWriter(handle, fieldnames=['received_time_ns', 'event_time_ms', 'episode', 'pre_mid'])
                writer.writeheader()
                writer.writerows(dict(received_time_ns=i * NS + 100_000_000,
                                      event_time_ms=i * 1000, episode=1, pre_mid=100.) for i in range(3))
            trades = [(NS // 2, 2., 100.), (NS + NS // 2, 3., 2000.)]
            with patch('src.simulation.flow_response.trade_tape', return_value=trades):
                result = windows(path, 'unused', max_message_age_ms=250.)
            self.assertEqual(len(result), 1)
            self.assertEqual(result[0]['signed_btc'], 2.)


if __name__ == '__main__':
    unittest.main()
