"""Descriptive follow-up; cannot promote a strategy on the already inspected test."""
import json
from pathlib import Path
import numpy as np
import pandas as pd
from .historical_month_research import ridge,predict,FEATURES

def run(root):
    root=Path(root);a=pd.read_csv(root/'five_minute_flow.csv');train=a[a.date<='2026-09-20'];test=a[a.date>='2026-09-26']
    edges=np.quantile(train.imbalance,[.1,.2,.3,.4,.5,.6,.7,.8,.9]);bins=np.searchsorted(edges,test.imbalance)
    groups=[]
    for i in range(10):
        g=test[bins==i];days=g.groupby('date').agg(same=('return_bps','mean'),future=('target_bps','mean'))
        rng=np.random.default_rng(73+i)
        def ci(k):return list(map(float,np.quantile(rng.choice(days[k].to_numpy(),(10000,len(days)),replace=True).mean(1),[.025,.975])))
        groups.append(dict(training_flow_decile=i+1,rows=len(g),mean_flow=float(g.imbalance.mean()),same_window_mean_bps=float(g.return_bps.mean()),next_window_mean_bps=float(g.target_bps.mean()),same_daily_mean_95=ci('same'),next_daily_mean_95=ci('future')))
    # Magnitude forecasting is exploratory and uses only training targets.
    train=train[train.exit_time<test.decision_time.min()-5*86400000]
    m=ridge(train[FEATURES].to_numpy(),np.log1p(np.abs(train.target_bps.to_numpy())))
    pred=predict(test[FEATURES].to_numpy(),m);actual=np.log1p(np.abs(test.target_bps.to_numpy()));base=np.log1p(np.abs(train.target_bps.to_numpy())).mean()
    result=dict(status='exploratory_descriptive_followup',qualified=False,flow_edges=edges.tolist(),test_flow_deciles=groups,log_absolute_return_forecast=dict(model_mse=float(np.mean((pred-actual)**2)),constant_mse=float(np.mean((base-actual)**2))),notes=['Follow-up designed after primary test results; not an independent confirmatory test.','Day-equal bootstrap intervals use five days and are weak uncertainty estimates; no multiple-comparison correction.','Contemporaneous association is not causality or a tradable forward signal.','Trade-count and volume describe anonymous activity, not participant identity.'])
    (root/'diagnostics.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2))
if __name__=='__main__':
    import sys
    run(sys.argv[1])
