import math
import unittest
from src.simulation.book_changes import best_quote_ofi
from src.simulation.ecology_price_mechanics import build_windows,bootstrap_mean,mutual_information,categories,contrast

class MechanicsStudyTests(unittest.TestCase):
    def book(self):
        return [dict(received_time_ns=i*100000000,event_time_ms=i*100,episode=1,exposure_seconds=.1,
                     post_best_bid=99.,post_best_ask=101.,post_mid=100.,post_bid_depth_10bps=10.,post_ask_depth_10bps=10.,
                     post_bid_top_qty=2.,post_ask_top_qty=2.,post_obi_top=0.,bid_add_qty=1.,bid_remove_qty=0.,ask_add_qty=0.,ask_remove_qty=0.,best_quote_ofi_btc=1.) for i in range(12)]
    def test_best_quote_ofi_queue_changes_and_price_moves(self):
        self.assertEqual(best_quote_ofi(100,2,101,3,100,4,101,1),4)
        self.assertEqual(best_quote_ofi(100,2,101,3,100.5,4,101,3),4)
        self.assertEqual(best_quote_ofi(100,2,101,3,99,4,101,3),-2)
        self.assertEqual(best_quote_ofi(100,2,101,3,100,2,102,7),3)
        self.assertEqual(best_quote_ofi(100,2,101,3,100,2,100.5,7),-7)
    def test_exact_boundaries_and_change_count(self):
        rows,audit=build_windows(self.book(),[(0,5.,0.),(500000000,2.,0.),(1000000000,-1.,0.)])
        self.assertEqual(len(rows),1);r=rows[0]
        self.assertEqual(r['buy_btc'],2);self.assertEqual(r['sell_btc'],1)
        self.assertEqual(r['bid_added_btc'],10);self.assertEqual(r['ofi_btc'],10)
        self.assertTrue(r['fresh_250ms']);self.assertIsNone(r['forward_1s_bps'])
    def test_gap_and_crossed_book_excluded(self):
        b=self.book();b[5]['exposure_seconds']=.5
        self.assertEqual(build_windows(b,[])[0],[])
    def test_missing_trade_payload_excludes_interval(self):
        rows,audit=build_windows(self.book(),[],[500000000])
        self.assertEqual(rows,[]);self.assertEqual(audit['missing_trade_payload'],1)
    def test_trade_id_gap_range_excludes_intersecting_window(self):
        rows,audit=build_windows(self.book(),[],missing_trade_ranges=[(400000000,700000000)])
        self.assertEqual(rows,[]);self.assertEqual(audit['trade_id_gap_windows'],1)
        b=self.book();b[5]['post_best_bid']=102.
        self.assertEqual(build_windows(b,[])[0],[])
    def test_probabilities_and_information(self):
        d=bootstrap_mean([1.,0.]*10,list(range(20)),list(range(25)))
        self.assertEqual(d['mean'],.5);self.assertGreaterEqual(d['lower'],0);self.assertLessEqual(d['upper'],1)
        self.assertAlmostEqual(mutual_information([-1,0,1],[-1,0,1]),math.log2(3))
        self.assertEqual(mutual_information([0,0,0],[-1,0,1]),0)
    def test_block_contrast_keeps_groups_in_same_resamples(self):
        groups={name:[dict(start_ns=i*60*1000000000,signed_btc=1,move_bps=value) for i in range(20)] for name,value in [('a',2),('b',1)]}
        result=contrast(groups,list(range(20)),'a','b')
        self.assertEqual(result['mean'],1);self.assertEqual(result['lower'],1);self.assertEqual(result['upper'],1)
    def test_book_opposition_is_distinct_from_trade_sign(self):
        row=dict(signed_btc=1,trade_pressure=.2,ofi_btc=-2,display_pressure=.1,start_depth_btc=10)
        tags=categories(row,dict(high_trade_pressure=.1,thin_depth_btc=20))
        self.assertIn('book_opposes',tags);self.assertIn('display_reinforces',tags)
