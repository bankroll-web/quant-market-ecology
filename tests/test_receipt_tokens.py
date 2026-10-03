import unittest
import numpy as np
import pandas as pd
from receipt_tokens import receipt_trade_windows, adapt_hour, receipt_samples

class ReceiptTests(unittest.TestCase):
    def test_late_trade_moves_to_later_window_and_ties_deferred(self):
        n, total, flow = receipt_trade_windows([10, 19, 20, 25, 30], [1, 2, 3, 4, 5],
                                               [False, True, False, False, True], [10, 20], [20, 30])
        self.assertEqual(n.tolist(), [2, 2])
        np.testing.assert_allclose(total, [3, 7])
        np.testing.assert_allclose(flow, [-1, 7])

    def test_future_trade_perturbation_does_not_change_past_features(self):
        a = receipt_trade_windows([11, 19, 40], [1, 2, 5], [False]*3, [10], [20])
        b = receipt_trade_windows([11, 19, 40, 50], [1, 2, 999, 9999], [False]*4, [10], [20])
        for x, y in zip(a, b):
            np.testing.assert_array_equal(x, y)

    def frame(self, n=50):
        return pd.DataFrame({'hour': ['test']*n, 'episode_id': ['a']*n,
                             'interval_index': np.arange(n), 't1_event_time_ms': np.arange(n)+1,
                             'received_time_ns': (np.arange(n)+1)*10**6+500,
                             'mid_t1': 100.+np.arange(n)/10})

    def test_receipt_reversal_rejected(self):
        df = self.frame()
        df.loc[20, 'received_time_ns'] = df.loc[19, 'received_time_ns']
        adapted = adapt_hour(df, [1], [1], [False])
        self.assertFalse(adapted.loc[0, 'receipt_valid'])
        self.assertFalse(adapted.loc[20, 'receipt_valid'])

    def test_samples_have_current_price_anchor_and_future_receipts(self):
        df = adapt_hour(self.frame(), [1], [1], [False])
        tokens = pd.DataFrame(np.zeros((len(df), 12), dtype=np.int64))
        sample = receipt_samples(df, tokens)
        self.assertTrue(np.all(sample[6] > sample[5]))
        np.testing.assert_allclose(sample[2], 10000*np.log(sample[8]/sample[7]))
        self.assertTrue(np.all(np.isnan(sample[3])))
        df['receipt_valid'] = False
        with self.assertRaises(ValueError):
            receipt_samples(df, tokens)

if __name__ == '__main__':
    unittest.main()
