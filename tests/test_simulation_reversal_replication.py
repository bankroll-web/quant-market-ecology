import unittest
import numpy as np
from src.simulation.ecology_reversal_replication import holm,stationary_indices
class ReplicationTests(unittest.TestCase):
    def test_holm_monotonic_adjustment(self):
        np.testing.assert_allclose(holm([.03,.01,.2]),[.06,.03,.2])
    def test_stationary_blocks_and_reproducibility(self):
        a=stationary_indices(31,draws=20,seed=91)
        np.testing.assert_array_equal(a,stationary_indices(31,draws=20,seed=91))
        self.assertTrue(((a>=0)&(a<31)).all())
        continued=(a[:,1:]==(a[:,:-1]+1)%31).mean()
        self.assertGreater(continued,.5)
        self.assertLess(continued,.85)
