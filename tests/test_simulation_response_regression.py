import csv
import tempfile
import unittest
from pathlib import Path

import numpy as np

from src.simulation.response_regression import evaluate, fit, predict, samples


class ResponseRegressionTest(unittest.TestCase):
    def test_model_is_fixed_after_fit_and_constant_feature_is_safe(self):
        train = [dict(x=[i, 0, i / 2], y=2 * i + 1) for i in range(8)]
        model = fit(train)
        original = repr(model)
        self.assertTrue(np.isfinite(predict(model, [dict(x=[100, 0, 50])])).all())
        evaluate(model, [dict(x=[100, 0, 50], y=-999)])
        self.assertEqual(repr(model), original)
        self.assertEqual(model['intercept_bps'], 8)

    def test_exact_join_initial_state_and_nonoverlapping_labels(self):
        with tempfile.TemporaryDirectory() as directory:
            book = Path(directory) / 'book.csv'
            flow = Path(directory) / 'flow.csv'
            states = [dict(received_time_ns=i * 1_000_000_000, episode=1,
                           pre_bid_depth_10bps=10, pre_ask_depth_10bps=10,
                           pre_obi_top=i / 10) for i in range(4)]
            windows = [dict(start_received_ns=i * 1_000_000_000,
                end_received_ns=(i + 1) * 1_000_000_000, episode=1,
                signed_btc=2, absolute_trade_btc=3, forward_1s_return_bps=1) for i in range(4)]
            for path, rows in ((book, states), (flow, windows)):
                with path.open('w', newline='') as handle:
                    writer = csv.DictWriter(handle, fieldnames=rows[0])
                    writer.writeheader(); writer.writerows(rows)
            result = samples(flow, book)
            self.assertEqual([r['start_ns'] for r in result], [0, 3_000_000_000])
            self.assertEqual(result[0]['x'][:2], [0.1, 0])
            self.assertEqual(result[1]['x'][1], 0.3)

    def test_zero_baseline_and_empty_sample(self):
        model = fit([dict(x=[i, 0, 0], y=0) for i in range(8)])
        score = evaluate(model, [dict(x=[1, 0, 0], y=2)])
        self.assertEqual(score['zero_rmse_bps'], 2)
        self.assertEqual(score['improvement_vs_zero_pct'], 0)
        self.assertIsNone(evaluate(model, [])['rmse_bps'])
