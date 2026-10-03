"""Exploratory trade-ecology response curves; anonymous flow, no causal labels."""
import json
from pathlib import Path
import numpy as np
import pandas as pd
from .historical_month_research import ridge,predict


def design(a,thresholds):
    flow=a.imbalance.to_numpy();activity=a.log_count.to_numpy()-thresholds['count_center'];volume=a.log_volume.to_numpy()-thresholds['volume_center']
    lag=a.imbalance.shift(1).to_numpy();memory=a.imbalance.rolling(3).mean().to_numpy()
    return np.column_stack([flow,lag,memory,a.return_bps,activity,volume,a.range_bps,flow*activity,flow*volume,flow*np.abs(flow)])


def response(a,h):
    future=a.close.shift(-h)
    y=10000*np.log(future/a.close)
    end=a.bucket.shift(-h)+300000
    return y,end


def clustered_interval(g,column,seed):
    days=g.groupby('date')[column].agg(['sum','count']).to_numpy()
    if len(days)<2:return None
    rng=np.random.default_rng(seed)
    indices=rng.integers(0,len(days),(5000,len(days)))
    sampled=days[indices];draws=sampled[:,:,0].sum(1)/sampled[:,:,1].sum(1)
    return list(map(float,np.quantile(draws,[.025,.975])))


def run(root):
    root=Path(root);a=pd.read_csv(root/'five_minute_flow.csv')
    if not np.all(np.diff(a.bucket)==300000):raise ValueError('Discontinuous observations')
    training=a[a.date<='2026-09-20']
    t=dict(flow_extreme=float(training.imbalance.abs().quantile(.8)),activity_high=float(training.log_count.quantile(.75)),count_center=float(training.log_count.mean()),volume_center=float(training.log_volume.mean()),low_move=float(training.return_bps.abs().quantile(.25)))
    x=design(a,t);boundary=pd.Timestamp('2026-09-21',tz='UTC').timestamp()*1000;results={}
    for h in [1,3,6]:
        y,end=response(a,h);ok=np.isfinite(x).all(1)&y.notna().to_numpy()
        tr=ok&(a.date<='2026-09-20').to_numpy()&(end<boundary).to_numpy()
        # Fixed clock subsampling: adjacent target intervals never overlap.
        ev=ok&(a.date>='2026-09-21').to_numpy()&(np.arange(len(a))%h==0)
        m=ridge(x[tr],y.to_numpy()[tr]);p=predict(x[ev],m);e=a[ev].copy();e['future']=y[ev];e['aligned']=np.sign(e.imbalance)*e.future;e['positive_aligned']=(e.aligned>0).astype(float)
        base=float(y[tr].mean());e['loss_difference']=(p-e.future)**2-(base-e.future)**2
        groups=[]
        extreme=e.imbalance.abs()>=t['flow_extreme'];active=e.log_count>=t['activity_high']
        # Low realized movement despite extreme flow is an observed label, not proof of absorption.
        for name,mask in [('strong_flow_high_activity',extreme&active),('strong_flow_normal_activity',extreme&~active),('strong_flow_low_current_move',extreme&(e.return_bps.abs()<=t['low_move']))]:
            g=e[mask];groups.append(dict(condition=name,rows=len(g),days=g.date.nunique(),mean_aligned_future_bps=float(g.aligned.mean()),probability_same_flow_direction=float(g.positive_aligned.mean()),aligned_day_cluster_95=clustered_interval(g,'aligned',h),direction_day_cluster_95=clustered_interval(g,'positive_aligned',h+10)))
        results[str(h*5)]=dict(training_rows=int(tr.sum()),evaluation_rows=int(ev.sum()),model_mse=float(np.mean((p-e.future.to_numpy())**2)),constant_mse=float(np.mean((base-e.future.to_numpy())**2)),loss_difference_day_cluster_95=clustered_interval(e,'loss_difference',h+20),conditional_responses=groups,model=m)
    result=dict(status='exploratory_conditional_ecology_response',qualified=False,thresholds=t,horizons_minutes=results,feature_names=['flow','lag_flow','three_block_flow_mean','current_return','centered_log_count','centered_log_volume','range','flow_x_activity','flow_x_volume','signed_squared_flow'],limits=['September was already examined. These models are exploratory, not untouched validation.','Price response uses last-trade close-to-close returns, not executable profits.','Five-minute labels do not identify traders, liquidity or cancellations. Low-move flow is not measured replenishment.','Longer-horizon evaluation is clock-subsampled to avoid overlapping target intervals; serial dependence remains.','Confidence intervals resample whole days and recompute observation-weighted means; ten days give limited uncertainty resolution.','No multiple-comparison correction or causal identification; independent replication required.'])
    (root/'conditional_responses.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps({k:{'mse':v['model_mse'],'baseline':v['constant_mse'],'conditions':v['conditional_responses']} for k,v in results.items()},indent=2))

if __name__=='__main__':
    import sys
    run(sys.argv[1])
