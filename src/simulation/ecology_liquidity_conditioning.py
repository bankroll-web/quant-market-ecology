"""Fixed historical liquidity/flow conditioning; no causal or trading promotion."""
import json,hashlib
from pathlib import Path
import numpy as np
import pandas as pd

def spaced_indices(valid,horizon):
    keep=[];next_ns=-1
    for i,r in valid.sort_values("end_ns").iterrows():
        if r.end_ns>=next_ns:
            keep.append(i);next_ns=int(r.end_ns)+horizon*10**9+250_000_000
    return keep

def run(root):
    root=Path(root);frames=[];inputs={}
    for folder in ['ecology_price_mechanics','mechanics_replication']:
        for p in sorted((root/'data/processed'/folder).glob('*_windows.csv')):
            inputs[str(p.relative_to(root))]=hashlib.sha256(p.read_bytes()).hexdigest()
            a=pd.read_csv(p);a['hour']=p.name.replace('_windows.csv','');frames.append(a)
    a=pd.concat(frames,ignore_index=True);a=a[a.fresh_250ms==True].copy()
    thresholds=json.loads((root/'docs/price_mechanics/summary.json').read_text())['thresholds']
    high=a.trade_pressure.abs()>=thresholds['high_trade_pressure'];thin=a.start_depth_btc<=thresholds['thin_depth_btc']
    a['state']=np.where(a.trade_pressure*a.display_pressure>0,'reinforcing',np.where(a.trade_pressure*a.display_pressure<0,'opposing','neutral'))
    a['thin']=thin;a=a[high];out=[]
    for horizon in [1,5]:
        col=f'forward_{horizon}s_bps'
        valid=a[a[col].notna()].sort_values('end_ns');keep=spaced_indices(valid,horizon)
        valid=valid.loc[keep].copy();valid['aligned']=np.sign(valid.trade_pressure)*valid[col]
        for subset in ['training','later_hours']:
            e=valid[(valid.hour=='2026-05-25_00') if subset=='training' else (valid.hour!='2026-05-25_00')]
            for state in ['reinforcing','opposing']:
                for depth in [True,False]:
                    g=e[(e.state==state)&(e.thin==depth)];by=g.groupby('hour').aligned.agg(['sum','count']);ci=None
                    if len(by)>1:
                        z=by.to_numpy();rng=np.random.default_rng(31);sample=z[rng.integers(len(z),size=(5000,len(z)))];v=sample[:,:,0].sum(1)/sample[:,:,1].sum(1);ci=list(map(float,np.quantile(v,[.025,.975])))
                    out.append(dict(horizon_seconds=horizon,subset=subset,state=state,depth='thin' if depth else 'thick',observations=len(g),hours=len(by),mean_aligned_forward_bps=float(g.aligned.mean()) if len(g) else None,hour_cluster_95=ci))
    result=dict(status='exploratory_liquidity_conditioning',qualified=False,input_sha256=inputs,thresholds=thresholds,results=out,limits=['All eight selected hours have previously been inspected; no untouched evaluation.','Anonymous net display changes are not measured cancellations or participant identity.','Receipt timing filters inherited from audited window construction; sparse forward labels constrain coverage.','Nonoverlapping target spacing enforced; hour resampling over few disconnected hours is weak uncertainty evidence.','Forward midpoint responses omit executable spread, fills, fees and latency.'])
    dest=root/'docs/history30/liquidity_conditioning.json';dest.write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(out,indent=2))
if __name__=='__main__':
    import sys
    run(sys.argv[1])
