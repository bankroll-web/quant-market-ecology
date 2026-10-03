import csv
import tempfile
import unittest
from pathlib import Path

from src.simulation.timing_audit import boundary, timing


class TimingTest(unittest.TestCase):
    def test_file_order_and_latency_are_distinct(self):
        result = timing([200_000_000, 100_000_000, 400_000_000], [0, 0, 0])
        self.assertEqual(result['receipt_backsteps_in_file'], 1)
        self.assertAlmostEqual(result['age_over_250ms_pct'], 100/3)
        self.assertEqual(result['distinct_receipt_cadence_median_ms'], 150)

    def test_boundary_never_compares_across_episode_gap(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)/'states.csv'
            rows = [dict(episode=1, received_time_ns=0, pre_mid=99, post_mid=100, exposure_seconds=.1),
                    dict(episode=1, received_time_ns=100_000_000, pre_mid=100, post_mid=101, exposure_seconds=.1),
                    dict(episode=2, received_time_ns=900_000_000, pre_mid=900, post_mid=901, exposure_seconds=.1)]
            with path.open('w', newline='') as handle:
                writer=csv.DictWriter(handle,fieldnames=rows[0]);writer.writeheader();writer.writerows(rows)
            result=boundary(path)
            self.assertEqual(result['post_to_next_pre_comparisons'],1)
            self.assertEqual(result['post_to_next_pre_mid_mismatches'],0)
            self.assertEqual(result['pre_state_label_age_median_ms'],100)
