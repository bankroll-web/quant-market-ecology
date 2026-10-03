import unittest
import numpy as np
import pandas as pd
from receipt_move_benchmark import (prior_percentile,build_targets,receipt_segments,
    MatchedTokenizer,lag_features,build_features)


def fixture():
    mid=np.array([100.,100.05,100.,100.,100.1,100.1])
    end=np.array([1000,1050,1100,1150,1200,1250])
    frame=pd.DataFrame(dict(hour='toy',episode_id=0,interval_index=np.arange(6),
        t1_event_time_ms=end-10,t0_event_time_ms=np.r_[980,end[:-1]-10],
        decision_receipt_ns=end*1_000_000,receipt_valid=True,
        mid_t1=mid,mid_t0=np.r_[100.,mid[:-1]],
        bid_depth5_t0=10.,ask_depth5_t0=20.,obi5_t0=-1/3,spread_t1=.1,
        total_flow_qty=1.,n_trades=1.,signed_flow_qty=.5,bid_net_response=1.,ask_net_response=0.,
        bid_add_0_5_qty=1.,bid_remove_0_5_qty=0.,ask_add_0_5_qty=0.,ask_remove_0_5_qty=1.))
    return frame


class Tests(unittest.TestCase):
    def test_any_move_reversal_and_half_tick_are_not_erased(self):
        f=fixture();segment=np.zeros(6,int)
        t=build_targets(f,segment,100)
        self.assertEqual(t['any_move'][0],1)
        self.assertEqual(t['endpoint_move'][0],0)
        self.assertEqual(t['return_bps'][0],0)
        half=build_targets(f,segment,50)
        self.assertEqual(half['endpoint_move'][0],1)
        self.assertEqual(half['up'][0],1)
        self.assertEqual(half['label_available_ns'].dtype,np.dtype('int64'))
        self.assertEqual(half['label_available_ns'][0],1_050_000_000)

    def test_no_target_crosses_gap_or_missing_coverage(self):
        f=fixture();segment=np.array([0,0,0,1,1,1])
        t=build_targets(f,segment,100)
        self.assertTrue(np.isnan(t['return_bps'][1]))
        self.assertTrue(np.isnan(t['return_bps'][-1]))
        self.assertEqual(t['label_available_ns'][-1],-1)

    def test_future_values_cannot_change_past_percentiles(self):
        x=np.arange(40,dtype=float)
        old=prior_percentile(x,window=20,minimum=4)
        changed=x.copy();changed[25:]=10000
        np.testing.assert_allclose(old[:25],prior_percentile(changed,20,4)[:25],equal_nan=True)
        self.assertEqual(old[4],1.)
        self.assertTrue(np.isnan(old[0]))

    def test_receipt_clock_and_interval_break_split_segments(self):
        f=fixture();segment,valid,_=receipt_segments(f)
        self.assertTrue(valid[:5].all());self.assertFalse(valid[-1])
        f.loc[2,'decision_receipt_ns']=f.loc[1,'decision_receipt_ns']
        segment,valid,_=receipt_segments(f)
        self.assertNotEqual(segment[1],segment[2])
        f=fixture();f.loc[2,'t1_event_time_ms']=0
        _,valid,_=receipt_segments(f);self.assertFalse(valid[2])

    def test_bins_train_only_and_raw_token_lags_match(self):
        frame=pd.DataFrame({'flow':[0.,1.,2.,3.,10000.],'depth_percentile':[.1,.2,.3,.4,.9]})
        mask=np.array([1,1,1,1,0],bool)
        a=MatchedTokenizer().fit(frame,mask)
        frame.loc[4,'flow']=-999999.
        b=MatchedTokenizer().fit(frame,mask)
        np.testing.assert_equal(a.edges['flow'],b.edges['flow'])
        segment=np.array([0,0,0,1,1])
        raw=lag_features(frame,segment,2);tokens=lag_features(a.transform(frame),segment,2)
        self.assertEqual(list(raw),list(tokens))
        self.assertTrue(np.isnan(raw.loc[3,'flow_L1']))

    def test_trade_size_reset_and_feature_prefix_invariance(self):
        f=fixture();f.loc[0,'total_flow_qty']=100.
        segment=np.array([0,0,0,1,1,1])
        F=build_features(f,segment)
        self.assertTrue(np.isnan(F.loc[3,'depth_in_prior_trades']))
        self.assertEqual(F.loc[4,'depth_in_prior_trades'],30.)
        changed=f.copy();changed.loc[4:,'total_flow_qty']=10000
        changed.loc[4:,'mid_t1']=10000
        np.testing.assert_allclose(F.loc[:3].to_numpy(),build_features(changed,segment).loc[:3].to_numpy(),equal_nan=True)


if __name__=='__main__':unittest.main()
