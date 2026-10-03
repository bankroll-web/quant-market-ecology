import unittest
from src.simulation.ecology_liquidity_response import enrich,describe
class LiquidityResponseTests(unittest.TestCase):
    def row(self,signed):
        return dict(start_depth_btc=100,bid_added_btc=10,bid_reduced_btc=12,ask_added_btc=20,ask_reduced_btc=10,display_pressure=-.12,signed_btc=signed,trade_pressure=signed/100,fresh_250ms='True',move_bps=0)
    def test_buy_resistance_and_sell_support(self):
        buy=enrich(self.row(1),.001);sell=enrich(self.row(-1),.001)
        self.assertEqual(buy['regime'],'high_opposes');self.assertEqual(sell['regime'],'high_reinforces')
        self.assertEqual(buy['metrics']['resistance_side_net_per_start_depth'],.1)
        self.assertEqual(sell['metrics']['support_side_net_per_start_depth'],.1)
        self.assertEqual(buy['metrics']['gross_turnover_per_start_depth'],.52)
    def test_reconciliation_and_nonnegative_guards(self):
        row=self.row(1);row['display_pressure']=0
        with self.assertRaises(ValueError):enrich(row,.001)
        row=self.row(1);row['bid_added_btc']=-1
        with self.assertRaises(ValueError):enrich(row,.001)
    def test_zero_signed_direction_is_missing(self):
        row=enrich(self.row(0),.001)
        self.assertIsNone(row['metrics']['resistance_side_net_per_start_depth'])
        self.assertEqual(describe([row])['metrics']['resistance_side_net_per_start_depth']['count'],0)
        self.assertEqual(describe([])['windows'],0)
