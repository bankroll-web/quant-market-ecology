"""Analytical, causality, episode-boundary and malformed-input checks."""
import math
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from src.model_research import ExponentialHawkes


class HawkesTests(unittest.TestCase):
    def model(self):
        return ExponentialHawkes([1, 2], [[0.2, 0.3], [0.4, 0.1]], 2)

    def test_analytic_cross_excitation(self):
        m = self.model()
        self.assertEqual(m.observe(0, 0), (1, 2))
        pre = m.observe(1, 1)
        self.assertAlmostEqual(pre[0], 1 + 0.2 * math.exp(-2))
        self.assertAlmostEqual(pre[1], 2 + 0.4 * math.exp(-2))
        post = m.intensity_at(1)
        self.assertAlmostEqual(post[0], pre[0] + 0.3)
        self.assertAlmostEqual(post[1], pre[1] + 0.1)

    def test_reset_and_read_only_queries(self):
        m = self.model()
        m.observe(10, 0)
        before = m.intensity_at(11)
        m.intensity_at(100)
        self.assertEqual(m.intensity_at(11), before)
        m.reset()
        self.assertEqual(m.observe(0, 1), (1, 2))

    def test_prefix_invariance(self):
        a, b = self.model(), self.model()
        prefix = [(0, 0), (0.1, 1), (0.4, 0)]
        left = [a.observe(t, k) for t, k in prefix]
        right = [b.observe(t, k) for t, k in prefix]
        b.observe(1, 1)
        self.assertEqual(left, right)

    def test_invalid_events_do_not_mutate(self):
        m = self.model()
        m.observe(1, 0)
        expected = m.intensity_at(2)
        for t, k in [(1, 1), (0, 0), (float('nan'), 0), (2, 5), (2, True)]:
            with self.assertRaises(ValueError):
                m.observe(t, k)
            self.assertEqual(m.intensity_at(2), expected)

    def test_invalid_parameters(self):
        for mu, alpha, beta in [([], [], 1), ([1], [[-1]], 1), ([1], [[1]], 1),
                                ([1], [[0]], 0), ([float('nan')], [[0]], 1),
                                ([1], [[float('inf')]], 1), ([1, 2], [[0]], 1)]:
            with self.assertRaises(ValueError):
                ExponentialHawkes(mu, alpha, beta)


if __name__ == '__main__':
    unittest.main()
