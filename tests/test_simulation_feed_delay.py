import unittest
from src.simulation.coinbase_observer import FeedDelayGuard

class FeedDelayTests(unittest.TestCase):
    def test_sustained_delay_switches_after_five_seconds(self):
        guard=FeedDelayGuard()
        self.assertFalse(guard.update(3_000_000_000,10))
        self.assertFalse(guard.update(3_000_000_000,14.9))
        self.assertTrue(guard.update(3_000_000_000,15))
    def test_recovery_resets_timer(self):
        guard=FeedDelayGuard()
        guard.update(3_000_000_000,0)
        self.assertFalse(guard.update(100_000_000,4))
        self.assertFalse(guard.update(3_000_000_000,5))
        self.assertFalse(guard.update(3_000_000_000,9))
    def test_clock_warning_also_fails_over(self):
        guard=FeedDelayGuard()
        self.assertFalse(guard.update(-1,0))
        self.assertTrue(guard.update(-1,5))
