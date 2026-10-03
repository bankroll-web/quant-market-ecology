import csv
import tempfile
import unittest
from pathlib import Path
import numpy as np
from src.simulation.strategy_research import load,fit,predict,paper

class StrategyResearchTests(unittest.TestCase):
    def test_quote_costs_and_short_accounting(self):
        rows=[dict(long_quote_bps=2.,short_quote_bps=-2.),dict(long_quote_bps=-3.,short_quote_bps=3.)]
        r=paper(rows,[1,-1],5.)
        self.assertEqual(r['summed_net_bps'],-5.)
        self.assertEqual(r['max_cumulative_drawdown_bps'],5.)
        self.assertEqual(paper(rows,[0,0])['trades'],0)

    def test_training_transform_and_future_rows_do_not_refit(self):
        rows=[dict(x=[i,0,1,2,3,4],y=float(i)/10) for i in range(20)]
        for kind in ('ridge','rbf_kernel_ridge'):
            m=fit(rows,kind);before=predict(m,rows).copy()
            predict(m,[dict(x=[1e8]*6,y=-1e8)])
            np.testing.assert_array_equal(before,predict(m,rows))
            self.assertEqual(m['scale'][1],1.)

    def fixture(self,directory,missing=False,future_obi=.9):
        fields=['received_time_ns','event_time_ms','episode','post_bid_depth_10bps','post_ask_depth_10bps','post_mid','post_obi_top','post_spread','post_best_bid','post_best_ask']
        book=[]
        for t in (1_000_000_000,1_100_000_000,6_000_000_000):
            book.append(dict(zip(fields,[t,t//1_000_000,2 if missing and t==6_000_000_000 else 1,5,5,100,.2 if t==1_000_000_000 else future_obi,2,99,101])))
        bp=directory/'book.csv';fp=directory/'flow.csv'
        with bp.open('w',newline='') as f:
            w=csv.DictWriter(f,fieldnames=fields);w.writeheader();w.writerows(book)
        flow=dict(start_received_ns=0,end_received_ns=1_000_000_000,episode=1,signed_btc=1,absolute_trade_btc=2,mid_log_return_bps=.5)
        with fp.open('w',newline='') as f:
            w=csv.DictWriter(f,fieldnames=flow);w.writeheader();w.writerow(flow)
        return fp,bp

    def test_future_book_does_not_enter_features_and_gap_exit_is_reported(self):
        with tempfile.TemporaryDirectory() as d:
            fp,bp=self.fixture(Path(d));a,audit=load(fp,bp)
            fp,bp=self.fixture(Path(d),future_obi=-.9);b,_=load(fp,bp)
            self.assertEqual(a[0]['x'],b[0]['x'])
            self.assertEqual(a[0]['x'][1],.2)
            self.assertEqual(a[0]['entry_ns'],1_100_000_000)
            fp,bp=self.fixture(Path(d),missing=True);rows,audit=load(fp,bp)
            self.assertEqual(rows,[]);self.assertEqual(audit['missing_exit'],1)
