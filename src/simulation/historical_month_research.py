"""Fixed thirty-day trade-flow experiment; no L2 or live execution claims."""
import argparse,hashlib,json,zipfile
from pathlib import Path
import numpy as np
import pandas as pd

FEATURES=['imbalance','return_bps','log_volume','log_count','range_bps']

def aggregate(path):
    parts=[];previous_id=None;previous_time=None;rows=0;gaps=0
    with zipfile.ZipFile(path) as z:
        name=z.namelist()[0]
        with z.open(name) as f:
            for c in pd.read_csv(f,chunksize=500000):
                c.columns=['id','price','qty','first','last','time','maker']
                ids=c.id.to_numpy();ts=c.time.to_numpy()
                if np.any(np.diff(ids)<=0) or np.any(np.diff(ts)<0):raise ValueError('Unordered trades')
                if previous_id is not None:
                    if ids[0]<=previous_id or ts[0]<previous_time:raise ValueError('Chunk ordering')
                    gaps+=int(ids[0]!=previous_id+1)
                gaps+=int(np.sum(np.diff(ids)!=1));previous_id=int(ids[-1]);previous_time=int(ts[-1]);rows+=len(c)
                if (c.price<=0).any() or (c.qty<=0).any():raise ValueError('Invalid trades')
                maker=c.maker.astype(str).str.lower()
                if not maker.isin(['true','false']).all():raise ValueError('Invalid side')
                c['signed']=np.where(maker=='true',-c.qty,c.qty)
                c['bucket']=c.time//300000*300000
                g=c.groupby('bucket',sort=True).agg(open=('price','first'),close=('price','last'),high=('price','max'),low=('price','min'),volume=('qty','sum'),signed=('signed','sum'),count=('id','size'),first_time=('time','first'),last_time=('time','last'))
                parts.append(g)
    a=pd.concat(parts).groupby(level=0,sort=True).agg({'open':'first','close':'last','high':'max','low':'min','volume':'sum','signed':'sum','count':'sum','first_time':'first','last_time':'last'})
    if not np.all(np.diff(a.index)==300000):raise ValueError('Missing five-minute buckets')
    a['imbalance']=a.signed/a.volume;a['return_bps']=10000*np.log(a.close/a.open)
    a['log_volume']=np.log(a.volume);a['log_count']=np.log(a['count']);a['range_bps']=10000*np.log(a.high/a.low)
    a['target_bps']=10000*(a.close.shift(-1)/a.open.shift(-1)-1)
    a['entry_time']=a.first_time.shift(-1);a['exit_time']=a.last_time.shift(-1)
    a['decision_time']=a.index+300000
    a['date']=pd.to_datetime(a.index,unit='ms',utc=True).strftime('%Y-%m-%d')
    a=a.iloc[:-1].copy()
    if not (a.entry_time>=a.decision_time).all():raise ValueError('Lookahead execution')
    return a,dict(aggregate_trades=rows,aggregate_id_gaps=gaps,first_ms=int(parts[0].first_time.iloc[0]),last_ms=int(previous_time))

def ridge(x,y):
    mean=x.mean(0);std=x.std(0);std=np.where(std>0,std,1)
    z=np.column_stack([np.ones(len(x)),(x-mean)/std]);pen=np.eye(z.shape[1]);pen[0,0]=0
    weights=np.linalg.solve(z.T@z+len(x)*.1*pen,z.T@y)
    return dict(mean=mean.tolist(),std=std.tolist(),weights=weights.tolist(),ridge=.1)

def predict(x,m):return np.column_stack([np.ones(len(x)),(x-np.array(m['mean']))/np.array(m['std'])])@np.array(m['weights'])

def metrics(a,p,buffer,cost=6,decision_cost=6):
    pos=np.where(p>decision_cost+buffer,1,np.where(p<-decision_cost-buffer,-1,0));net=pos*a.target_bps.to_numpy()-np.abs(pos)*cost
    daily=pd.Series(net,index=a.date).groupby(level=0).sum()
    return dict(trades=int(np.count_nonzero(pos)),sum_trade_return_bps=float(net.sum()),mean_trade_net_bps=float(net[pos!=0].mean()) if np.any(pos) else None,positive_days=int((daily>0).sum()),days=len(daily),daily_sum_bps={str(k):float(v) for k,v in daily.items()})

def run(path,out):
    a,audit=aggregate(path);dates=sorted(a.date.unique())
    if len(dates)!=30:raise ValueError('Require exactly thirty calendar days')
    train=a[a.date.isin(dates[:20]) & (a.exit_time<pd.Timestamp(dates[20],tz='UTC').timestamp()*1000)]
    validation=a[a.date.isin(dates[20:25]) & (a.exit_time<pd.Timestamp(dates[25],tz='UTC').timestamp()*1000)]
    test=a[a.date.isin(dates[25:])]
    x=lambda d:d[FEATURES].to_numpy();model=ridge(x(train),train.target_bps.to_numpy())
    pv=predict(x(validation),model);candidates={str(b):metrics(validation,pv,b) for b in [0,2,5]}
    buffer=max([0,2,5],key=lambda b:candidates[str(b)]['sum_trade_return_bps'])
    # No-trade wins any nonpositive validation result; never activate on test results.
    enabled=candidates[str(buffer)]['sum_trade_return_bps']>0
    pt=predict(x(test),model);effective=pt if enabled else np.zeros(len(pt))
    daymeans=pd.Series((pt-test.target_bps.to_numpy())**2-(test.target_bps.to_numpy())**2,index=test.date).groupby(level=0).mean().to_numpy()
    rng=np.random.default_rng(37);boots=np.mean(rng.choice(daymeans,(10000,len(daymeans)),replace=True),axis=1)
    result=dict(status='historical_trade_flow_development_study',qualified=False,features=FEATURES,audit=audit,source_sha256=hashlib.sha256(Path(path).read_bytes()).hexdigest(),dates=dates,splits=dict(training_rows=len(train),validation_rows=len(validation),test_rows=len(test)),model=model,validation_candidates=candidates,selected_buffer_bps=buffer,policy_enabled_by_validation=bool(enabled),test=dict(model_mse=float(np.mean((pt-test.target_bps.to_numpy())**2)),zero_mse=float(np.mean(test.target_bps.to_numpy()**2)),training_mean_mse=float(np.mean((train.target_bps.mean()-test.target_bps.to_numpy())**2)),mse_difference_daily_bootstrap_95=list(map(float,np.quantile(boots,[.025,.975]))),policy=metrics(test,effective,buffer),cost_sensitivity={str(c):metrics(test,effective,buffer,c) for c in [2,6,12]}),associations=dict(training_contemporaneous_flow_return=float(train.imbalance.corr(train.return_bps)),training_forward_flow_return=float(train.imbalance.corr(train.target_bps))),limitations=['Trade-flow only: no order book, maker cancellation or queue reconstruction.','Exchange event times only; no historical receipt timestamps.','First next-block trade and last trade are idealized execution proxies, not executable bid/ask fills.','Costs 2 bps per side fees plus 1 bp per side slippage are assumptions; funding and market impact omitted.','Sum of trade bps is an additive unit-exposure research score, not account return.','Five test days give weak regime coverage and bootstrap uncertainty.','Data inspected during this run; future independent replication still required.'])
    out=Path(out);out.mkdir(parents=True,exist_ok=True);a.to_csv(out/'five_minute_flow.csv');(out/'results.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2))

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('archive');p.add_argument('out');args=p.parse_args();run(args.archive,args.out)
