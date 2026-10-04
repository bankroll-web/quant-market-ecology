import unittest

import numpy as np
import pandas as pd

from censoring_report import censoring_report, wilson_interval
from sample_uniqueness import (average_uniqueness, effective_sample_size,
                               sparse_sample, uniqueness_weights)


def _synthetic(n, censor_prob_fn, seed=0):
    rng = np.random.default_rng(seed)
    vol = rng.uniform(1, 100, n)
    cens = rng.random(n) < censor_prob_fn(vol)
    return pd.DataFrame({
        "decision_ns": np.arange(n, dtype=np.int64) * 60_000_000_000,
        "vol_bps": vol,
        "status": np.where(cens, "censored", "labeled"),
        "reason": np.where(cens, "gap", ""),
        "label": np.where(cens, np.nan, rng.choice([-1, 0, 1], n)),
    })


class UniquenessTests(unittest.TestCase):
    def test_disjoint_events_fully_unique(self):
        u = average_uniqueness([0, 10], [10, 20])
        np.testing.assert_allclose(u, [1.0, 1.0])

    def test_identical_events_share_half(self):
        u = average_uniqueness([0, 0], [10, 10])
        np.testing.assert_allclose(u, [0.5, 0.5])

    def test_partial_overlap_known_value(self):
        # [0,10) and [5,15): each has 5 ns alone and 5 ns shared -> (5*1+5*.5)/10
        u = average_uniqueness([0, 5], [10, 15])
        np.testing.assert_allclose(u, [0.75, 0.75])

    def test_nested_event(self):
        # outer [0,10) contains inner [2,4): outer 8 alone + 2 shared -> 0.9
        u = average_uniqueness([0, 2], [10, 4])
        np.testing.assert_allclose(u, [0.9, 0.5])

    def test_effective_size_and_weights(self):
        s, e = [0, 0, 20], [10, 10, 30]
        self.assertAlmostEqual(effective_sample_size(s, e), 2.0)
        w = uniqueness_weights(s, e)
        self.assertAlmostEqual(w.sum(), 3.0)

    def test_sparse_sample_is_non_overlapping(self):
        s = np.array([0, 3, 10, 12])
        e = np.array([5, 8, 14, 20])
        keep = sparse_sample(s, e)
        for a, b in zip(keep[:-1], keep[1:]):
            self.assertLessEqual(e[a], s[b])
        self.assertEqual(list(keep), [0, 2])

    def test_bad_input_rejected(self):
        with self.assertRaises(ValueError):
            average_uniqueness([5], [1])


class CensoringTests(unittest.TestCase):
    def test_wilson_bounds(self):
        lo, hi = wilson_interval(0, 50)
        self.assertAlmostEqual(lo, 0.0, places=9)
        self.assertGreater(hi, 0.0)
        lo, hi = wilson_interval(25, 50)
        self.assertLess(lo, 0.5)
        self.assertGreater(hi, 0.5)

    def test_flags_censoring_that_rises_with_vol(self):
        df = _synthetic(6000, lambda v: 0.02 + 0.30 * v / 100)
        rep = censoring_report(df)
        self.assertTrue(any("RISES WITH VOLATILITY" in f for f in rep["flags"]))

    def test_no_flag_when_censoring_independent_of_vol(self):
        df = _synthetic(6000, lambda v: np.full_like(v, 0.05))
        rep = censoring_report(df)
        self.assertFalse(any("VOLATILITY" in f for f in rep["flags"]))

    def test_detects_long_outage_run(self):
        df = _synthetic(500, lambda v: np.zeros_like(v))
        df.loc[100:139, "status"] = "censored"
        df.loc[100:139, "reason"] = "book_reset"
        rep = censoring_report(df)
        self.assertEqual(rep["runs"]["longest_run"], 40)
        self.assertTrue(any("OUTAGE" in f for f in rep["flags"]))

    def test_constant_volatility_is_reported(self):
        df = _synthetic(100, lambda v: np.zeros_like(v))
        df["vol_bps"] = 0.0
        rep = censoring_report(df)
        self.assertEqual(len(rep["by_volatility"]), 1)
        self.assertEqual(rep["by_volatility"].iloc[0]["attempts"], 100)

    def test_nan_vol_rejected(self):
        df = _synthetic(100, lambda v: np.zeros_like(v))
        df.loc[3, "vol_bps"] = np.nan
        with self.assertRaises(ValueError):
            censoring_report(df)


if __name__ == "__main__":
    unittest.main()
