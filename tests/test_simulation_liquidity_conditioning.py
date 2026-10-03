import unittest
import pandas as pd
from src.simulation.ecology_liquidity_conditioning import spaced_indices
class SpacingTests(unittest.TestCase):
    def test_conservative_forward_endpoint_spacing(self):
        a=pd.DataFrame(dict(end_ns=[0,1_000_000_000,1_250_000_000,2_500_000_000]))
        self.assertEqual(spaced_indices(a,1),[0,2,3])
