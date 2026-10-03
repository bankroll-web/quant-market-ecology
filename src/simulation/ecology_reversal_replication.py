"""Frozen backward-period replication with stationary daily bootstrap and Holm."""
import json,hashlib
from pathlib import Path
import numpy as np
import pandas as pd
from .historical_month_research import aggregate
from .ecology_conditional_response import response

def stationary_indices(n,draws=5000,block=3,seed=91):
    rng=np.random.default_rng(seed);idx=np.empty((draws,n),dtype=int);idx[:,0]=rng.integers(n,size=draws)
    for j in range(1,n):idx[:,j]=np.where(rng.random(draws)<1/block,rng.integers(n,size=draws),(idx[:,j-1]+1)%n)
    return idx

def holm(p):
    order=np.argsort(p);out=np.empty(len(p));running=0
    for k,i in enumerate(order):running=max(running,min(1,(len(p)-k)*p[i]));out[i]=running
    return out.tolist()

def run(archive,root):
    root=Path(root);a,audit=aggregate(archive);a=a.reset_index();a.to_csv(root/'replication/august_five_minute_flow.csv',index=False)
    t=json.loads((root/'results/conditional_responses.json').read_text())['thresholds'];days=sorted(a.date.unique())
    if len(days)!=31 or days[0]!='2026-08-01' or days[-1]!='2026-08-31':raise ValueError('Wrong replication period')
    idx=stationary_indices(len(days));results=[]
    for h in [1,3,6]:
        y,end=response(a,h);mask=y.notna()&(a.imbalance.abs()>=t['flow_extreme'])&(a.log_count>=t['activity_high'])&(np.arange(len(a))%h==0)
        g=a[mask].copy();g['gross']=-np.sign(g.imbalance)*y[mask];g['net']=g.gross-6;g['win']=(g.net>0).astype(float)
        daily=g.groupby('date').agg(gross=('gross','sum'),net=('net','sum'),count=('net','size'),wins=('win','sum')).reindex(days,fill_value=0)
        counts=daily['count'].to_numpy();nets=daily.net.to_numpy();total=counts.sum();mean=nets.sum()/total if total else 0
        sampled_counts=counts[idx].sum(1);valid=sampled_counts>0
        boot=nets[idx].sum(1)[valid]/sampled_counts[valid]
        centered=nets-mean*counts;null=centered[idx].sum(1)[valid]/sampled_counts[valid]
        p=(1+np.sum(null>=mean))/(len(null)+1)
        results.append(dict(horizon_minutes=h*5,trades=int(total),active_days=int((counts>0).sum()),gross_mean_bps=float(g.gross.mean()),net_mean_bps=float(mean),net_mean_95=list(map(float,np.quantile(boot,[.025,.975]))),net_win_fraction=float(g.win.mean()),centered_bootstrap_one_sided_p=float(p),cost_sensitivity_mean_bps={str(c):float(g.gross.mean()-c) for c in [2,6,12]},daily={d:dict(gross_sum_bps=float(row.gross),net_sum_bps=float(row.net),trades=int(row['count'])) for d,row in daily.iterrows()}))
    adjusted=holm([r['centered_bootstrap_one_sided_p'] for r in results])
    for r,p in zip(results,adjusted):r['holm_adjusted_p']=p
    with Path(archive).open('rb') as f:sha=hashlib.file_digest(f,'sha256').hexdigest()
    result=dict(status='backward_cross_period_replication',qualified=False,archive_sha256=sha,audit=audit,thresholds=t,results=results,bootstrap=dict(draws=5000,mean_day_block=3,seed=91),limits=['August precedes September development: not forward or live validation.','Last-trade proxy fills, no spread/funding/impact/receipt latency. Costs assumed.','Thirty-one days may not support stationary-bootstrap assumptions across regimes.','Holm controls only three frozen horizons, not all previous research searches.','Linear bps scores are not compounded account returns. No trading promotion.'])
    (root/'replication/results.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps({k:v for k,v in result.items() if k!='results'},indent=2));print(json.dumps([{k:v for k,v in r.items() if k!='daily'} for r in results],indent=2))
if __name__=='__main__':
    import sys
    run(sys.argv[1],sys.argv[2])
