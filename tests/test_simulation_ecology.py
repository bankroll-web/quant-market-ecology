"""Invariants and paired-counterfactual check for the isolated simulation module."""
import json
import unittest
from pathlib import Path

from src.simulation.ecology import Book, common_flow, run, SHOCK_SECOND, SHOCK_QTY


class SimulationEcologyTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        root = Path(__file__).resolve().parents[1]
        cls.params = json.loads((root / "configs/simulation_v1_demo.json").read_text())[
            "calibration_from_valid_samples"
        ]

    def test_initial_depth_and_uncrossed_book(self):
        book = Book(self.params)
        state = book.state(-1, "test")
        self.assertAlmostEqual(state["bid_depth_btc"], self.params["depth_bid_10bps"])
        self.assertAlmostEqual(state["ask_depth_btc"], self.params["depth_ask_10bps"])
        self.assertAlmostEqual(state["spread"], 0.1)

    def test_paired_withdrawal_changes_impact_and_keeps_valid_book(self):
        flow = common_flow(self.params, 7)
        normal, normal_shock = run(self.params, flow, False)
        withdrawn, withdrawn_shock = run(self.params, flow, True)
        for a, b in zip(normal[:SHOCK_SECOND], withdrawn[:SHOCK_SECOND]):
            self.assertEqual({k: v for k, v in a.items() if k != "scenario"},
                             {k: v for k, v in b.items() if k != "scenario"})
        self.assertAlmostEqual(normal_shock["filled_qty_btc"], SHOCK_QTY)
        self.assertAlmostEqual(withdrawn_shock["filled_qty_btc"], SHOCK_QTY)
        self.assertGreater(withdrawn_shock["slippage_vs_pre_ask_bps"],
                           normal_shock["slippage_vs_pre_ask_bps"])
        self.assertLess(withdrawn_shock["ask_depth_10s_after_btc"],
                        normal_shock["ask_depth_10s_after_btc"])
        for row in normal + withdrawn:
            self.assertLess(row["bid"], row["ask"])
            self.assertGreaterEqual(row["bid_depth_btc"], 0)
            self.assertGreaterEqual(row["ask_depth_btc"], 0)


if __name__ == "__main__":
    unittest.main()
