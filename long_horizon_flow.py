"""Fixed historical trade-flow experiment. No real orders or order-book claims."""
import argparse, calendar, hashlib, json, zipfile
from pathlib import Path
import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingClassifier, HistGradientBoostingRegressor
from sklearn.metrics import log_loss, mean_squared_error

SPEC={'version':'long-flow-v1','data':'Binance BTCUSDT spot 1-minute public aggregates, June-August 2024','features':'completed-minute taker buy fraction, trade intensity, volume and mean trade size; 1/5/15/60-minute summaries; no participant identities or book depth','train':'June-July 2024','validation':'August 1-14 2024','evaluation':'August 15-31 2024, new to this recipe but not claimed globally untouched','horizons_minutes':[5,15,60],'decision_stride_minutes':60,'entry':'open two rows after feature minute (one complete minute delay after close)','exit':'open horizon minutes after entry','purge':'training and validation label exit strictly before next split','models':['training class-frequency and mean-return baselines','numeric gradient boosting','16-bin training-only token gradient boosting'],'thresholds_bps':[6,10,20],'primary_round_trip_cost_bps':6,'cost_scenarios_bps':[6,12,20],'selection':'validation mean net bps/day at primary cost, choose one model/horizon/threshold once; stay flat if no candidate positive','trading':'long/flat only, nonoverlapping hourly decisions, constant unit notional; cost scenarios include assumed total friction, not verified executable fills','limitations':['Aggregated historical trade flow, not event tokens or a transformer.','No receipt timestamps, book spreads, queues, actual fees or slippage; execution is a delayed price proxy.','Prior project has inspected 2024 daily data; evaluation is not guaranteed untouched project-wide.','No funding or short selling. Bootstrap by day is exploratory with 17 evaluation days.']}

def load(root):
 frames=[];manifest=[]
 for m in [6,7,8]:
  p=root/f'BTCUSDT-1m-2024-{m:02d}.zip';sha=hashlib.sha256(p.read_bytes()).hexdigest();assert sha==(root/(p.name+'.CHECKSUM')).read_text().split()[0]
  with zipfile.ZipFile(p) as z:d=pd.read_csv(z.open(z.namelist()[0]),header=None)
  assert len(d)==calendar.monthrange(2024,m)[1]*1440
  frames.append(d);manifest.append({'file':p.name,'sha256':sha,'rows':len(d),'url':'https://data.binance.vision/data/spot/monthly/klines/BTCUSDT/1m/'+p.name})
 d=pd.concat(frames,ignore_index=True);t=pd.to_datetime(d[0],unit='ms',utc=True);assert (np.diff(d[0])==60000).all()
 for k in [1,2,3,4,5,7,9,10]:assert np.isfinite(d[k]).all()
 assert (d[5]>0).all() and (d[9]>=0).all() and (d[9]<=d[5]).all()
 return d,t,manifest

def features(d):
 v=d[5];q=d[7];n=d[8];buy=d[9];x={}
 for w in [1,5,15,60]:
  vol=v.rolling(w,min_periods=w).sum();count=n.rolling(w,min_periods=w).sum()
  x[f'flow_{w}']=(2*buy.rolling(w,min_periods=w).sum()-vol)/vol
  x[f'log_volume_{w}']=np.log1p(vol/w);x[f'log_count_{w}']=np.log1p(count/w)
  x[f'log_trade_size_{w}']=np.log1p(q.rolling(w,min_periods=w).sum()/count)
 return pd.DataFrame(x)

def tokenize(train,allx):
 edges=[np.unique(np.quantile(train[:,j],np.arange(1,16)/16)) for j in range(train.shape[1])]
 return np.column_stack([np.searchsorted(e,allx[:,j],side='right') for j,e in enumerate(edges)]),[e.tolist() for e in edges]

def daily(t,y,pred,h,threshold,cost,start,end):
 dates=pd.date_range(start,end,freq='D',tz='UTC');r=pd.Series(0.,index=dates)
 take=pred>threshold
 for day,value in zip(t.dt.floor('D')[take],(y-cost)[take]):r.loc[day]+=float(value)
 return r

def run(root,out):
 out.mkdir(parents=True,exist_ok=True);spec=out/'SPEC.json'
 if spec.exists():assert json.loads(spec.read_text())==SPEC
 else:spec.write_text(json.dumps(SPEC,indent=2)+'\n')
 d,t,manifest=load(root);x=features(d);idx=np.arange(59,len(d)-62,60);x=x.iloc[idx].to_numpy();tt=t.iloc[idx].reset_index(drop=True);entry=idx+2
 boundary=pd.Timestamp('2024-08-01',tz='UTC');seal=pd.Timestamp('2024-08-15',tz='UTC');end=pd.Timestamp('2024-09-01',tz='UTC')
 candidates=[];models={};metrics=[];prediction_records=[];trial=0
 for h in SPEC['horizons_minutes']:
  exit_=entry+h;y=10000*np.log(d[1].to_numpy()[exit_]/d[1].to_numpy()[entry]);label_time=t.iloc[exit_].reset_index(drop=True)
  tr=(label_time<boundary).to_numpy();va=((tt>=boundary)&(label_time<seal)).to_numpy();te=((tt>=seal)&(label_time<end)).to_numpy()
  tokens,edges=tokenize(x[tr],x);(out/f'bins_{h}.json').write_text(json.dumps(edges))
  prior=float((y[tr]>0).mean());mean=float(y[tr].mean())
  for name,xx in [('numeric',x),('tokens',tokens)]:
   kwargs=dict(max_iter=100,max_leaf_nodes=15,min_samples_leaf=40,l2_regularization=2,learning_rate=.05,early_stopping=False,random_state=17)
   reg=HistGradientBoostingRegressor(**kwargs).fit(xx[tr],y[tr]);clf=HistGradientBoostingClassifier(**kwargs).fit(xx[tr],y[tr]>0);trial+=2
   pred=reg.predict(xx);prob=clf.predict_proba(xx)[:,1];models[h,name]=(pred,y,te)
   for split,mask in [('validation',va),('evaluation',te)]:
    metrics.append(dict(horizon=h,model=name,split=split,n=int(mask.sum()),log_loss=float(log_loss(y[mask]>0,prob[mask],labels=[False,True])),baseline_log_loss=float(log_loss(y[mask]>0,np.full(mask.sum(),prior),labels=[False,True])),mse=float(mean_squared_error(y[mask],pred[mask])),baseline_mse=float(mean_squared_error(y[mask],np.full(mask.sum(),mean)))))
   for threshold in SPEC['thresholds_bps']:
    r=daily(tt[va].reset_index(drop=True),y[va],pred[va],h,threshold,6,'2024-08-01','2024-08-14');candidates.append(dict(horizon=h,model=name,threshold=threshold,validation_bps_day=float(r.mean()),validation_trades=int((pred[va]>threshold).sum())))
   for i in np.flatnonzero(te):prediction_records.append(dict(decision=tt[i].isoformat(),entry=t.iloc[entry[i]].isoformat(),exit=t.iloc[exit_[i]].isoformat(),horizon=h,model=name,predicted_bps=float(pred[i]),prob_up=float(prob[i]),actual_bps=float(y[i])))
 selected=max(candidates,key=lambda r:r['validation_bps_day']);result={'spec':SPEC,'sources':manifest,'model_fits':trial,'policy_candidates':len(candidates),'metrics':metrics,'validation_candidates':candidates,'selected':selected,'qualified':False,'orders_enabled':False}
 if selected['validation_bps_day']>0:
  h=selected['horizon'];pred,y,mask=models[h,selected['model']];rng=np.random.default_rng(17);scores=[]
  for cost in SPEC['cost_scenarios_bps']:
   r=daily(tt[mask].reset_index(drop=True),y[mask],pred[mask],h,selected['threshold'],cost,'2024-08-15','2024-08-31');boot=r.to_numpy()[rng.integers(0,len(r),size=(10000,len(r)))].mean(axis=1)
   scores.append(dict(cost_bps=cost,mean_bps_day=float(r.mean()),total_bps=float(r.sum()),positive_days=int((r>0).sum()),days=len(r),trades=int((pred[mask]>selected['threshold']).sum()),bootstrap_mean_95_ci=np.quantile(boot,[.025,.975]).tolist(),daily_bps={str(k.date()):float(v) for k,v in r.items()}))
  result['selected_evaluation']=scores
 else:result['selected_evaluation']='No positive validation candidate; flat policy selected.'
 pd.DataFrame(prediction_records).to_csv(out/'predictions.csv.gz',index=False);(out/'RESULTS.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps({k:v for k,v in result.items() if k in ['selected','selected_evaluation','model_fits','policy_candidates']},indent=2))
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--data',type=Path,default=Path('data/raw/long_horizon'));p.add_argument('--out',type=Path,default=Path('docs/long_horizon_flow'));a=p.parse_args();run(a.data,a.out)
