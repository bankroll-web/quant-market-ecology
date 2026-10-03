import unittest
import numpy as np
from src.simulation.market_tokens import fit_tokenizer,encode_frame,contexts

class TokenTests(unittest.TestCase):
    def test_field_identity_and_extreme_flags(self):
        m=fit_tokenizer(np.tile(np.linspace(-1,1,100)[:,None],(1,8)))
        normal=encode_frame([0]*8,m);extreme=encode_frame([100]*8,m)
        self.assertEqual(len(set(normal)),8)
        self.assertTrue(all((t-3)%18==17 for t in extreme))
        self.assertEqual(m['upper'],[1]*8)
    def test_gap_and_episode_reset(self):
        m=fit_tokenizer(np.tile(np.linspace(-1,1,100)[:,None],(1,8)))
        def row(t,ep=1):
            return dict(received_time_ns=t,event_time_ms=0,episode=ep,post_best_bid=99,post_best_ask=101,post_bid_depth_10bps=1,post_ask_depth_10bps=1,post_mid=100,post_spread=2,post_obi_top=0,best_quote_ofi_btc=0,bid_add_qty=0,bid_remove_qty=0,ask_add_qty=0,ask_remove_qty=0)
        rows=[row(100_000_000),row(200_000_000),row(600_000_000),row(700_000_000,2),row(800_000_000,2)]
        c=list(contexts(rows,m,length=2))
        self.assertEqual([r['end_ns'] for r in c],[200_000_000,800_000_000])
    def test_future_event_invalidates_context(self):
        m=fit_tokenizer(np.zeros((10,8)))
        r=dict(received_time_ns=1,event_time_ms=1,episode=1,post_best_bid=1,post_best_ask=2,post_bid_depth_10bps=1,post_ask_depth_10bps=1)
        self.assertEqual(list(contexts([r],m,length=1)),[])
if __name__=='__main__':unittest.main()
