"""Fixed flow/activity interaction study, not causal attribution or execution."""
import argparse,hashlib,json,zipfile,calendar
from pathlib import Path
import numpy as np
import pandas as pd
from long_horizon_flow import daily
SPEC={'version':'flow-activity-v1','primary_horizon_minutes':15,'secondary_horizons_minutes':[5,60],'flow_window_minutes':15,'pressure_threshold':.20,'activity_reference':'mean trades/minute over strictly prior 1440 completed minutes','activity_window_minutes':15,'busy_ratio':1.5,'quiet_ratio':2/3,'decision_spacing_minutes':60,'entry_delay':'one complete minute after feature minute end','development':'June-July 2024','diagnostic_validation':'August 2024, already inspected','evaluation':'September 2024, new to this recipe but not guaranteed globally untouched','primary_hypothesis':'signed return following strong buying/selling pressure differs between busy and quiet periods','fixed_paper_rule':'long/flat: strong positive pressure (>0.20), busy activity (>1.5 times prior-day mean), hold 15 minutes','roundtrip_cost_scenarios_bps':[6,12,20],'no_threshold_selection':True,'no_live_orders':True,'limits':['Trade aggregates lack order-book liquidity and participant identity.','Observational response is not causal; signed response is not an executable short strategy.','Hourly examples can remain dependent across days; day bootstrap is an exploratory estimate.','Fixed thresholds are research choices, not optimized or established economic constants.']}

def causal_features(d):
 v=d[5];n=d[8].astype(float);flow=(2*d[9].rolling(15,min_periods=15).sum()-v.rolling(15,min_periods=15).sum())/v.rolling(15,min_periods=15).sum()
 ref=n.shift(1).rolling(1440,min_periods=1440).mean();rate=n.rolling(15,min_periods=15).mean()/ref
 return pd.DataFrame({'flow':flow,'activity_ratio':rate})

def interval(values,rng):
 a=np.asarray(values,float)
 if len(a)<2:return None
 means=a[rng.integers(0,len(a),(10000,len(a)))].mean(axis=1)
 return np.quantile(means,[.025,.975]).tolist()

def study(root,out):
 out.mkdir(parents=True,exist_ok=True);spec=out/'SPEC.json'
 if spec.exists():assert json.loads(spec.read_text())==SPEC
 else:spec.write_text(json.dumps(SPEC,indent=2)+'\n')
 fs=[];sources=[]
 for m in [6,7,8,9]:
  p=root/f'BTCUSDT-1m-2024-{m:02d}.zip';sha=hashlib.sha256(p.read_bytes()).hexdigest();assert sha==(root/(p.name+'.CHECKSUM')).read_text().split()[0]
  with zipfile.ZipFile(p) as z:a=pd.read_csv(z.open(z.namelist()[0]),header=None)
  assert len(a)==calendar.monthrange(2024,m)[1]*1440;fs.append(a);sources.append({'file':p.name,'sha256':sha,'rows':len(a)})
 d=pd.concat(fs,ignore_index=True);assert (np.diff(d[0])==60000).all();assert (d[5]>0).all() and ((d[9]>=0)&(d[9]<=d[5])).all()
 f=causal_features(d);idx=np.arange(1499,len(d)-62,60);t=pd.Series(pd.to_datetime(d[0].iloc[idx].to_numpy(),unit='ms',utc=True));f=f.iloc[idx].reset_index(drop=True);records=[];rows=[];rng=np.random.default_rng(23)
 periods=[('development','2024-06-01','2024-08-01'),('diagnostic_validation','2024-08-01','2024-09-01'),('evaluation','2024-09-01','2024-10-01')]
 for h in [15,5,60]:
  entry=idx+2;exit_=entry+h;exit_t=pd.Series(pd.to_datetime(d[0].iloc[exit_].to_numpy(),unit='ms',utc=True));ret=10000*np.log(d[1].to_numpy()[exit_]/d[1].to_numpy()[entry])
  for period,start,end in periods:
   m=((t>=pd.Timestamp(start,tz='UTC'))&(exit_t<pd.Timestamp(end,tz='UTC'))).to_numpy();strong=np.abs(f['flow'].to_numpy())>.2;signed=np.sign(f['flow'].to_numpy())*ret;day=t.dt.floor('D');groups={};means={}
   for name,g in [('busy',f.activity_ratio.to_numpy()>1.5),('quiet',f.activity_ratio.to_numpy()<2/3)]:
    take=m&strong&g;a=pd.DataFrame({'day':day[take].to_numpy(),'signed_bps':signed[take]});byday=a.groupby('day').signed_bps.mean();groups[name]={'n':int(take.sum()),'active_days':len(byday),'mean_signed_bps':float(signed[take].mean()) if take.any() else None,'equal_day_mean_signed_bps':float(byday.mean()) if len(byday) else None,'day_bootstrap_95_ci':interval(byday,rng)};means[name]=byday
   paired=pd.concat([means['busy'].rename('busy'),means['quiet'].rename('quiet')],axis=1).dropna();diff=paired.busy-paired.quiet
   records.append({'period':period,'horizon':h,'groups':groups,'paired_days':len(diff),'paired_busy_minus_quiet_bps':float(diff.mean()) if len(diff) else None,'paired_day_bootstrap_95_ci':interval(diff,rng)})
  for j in range(len(t)):
   if t[j]>=pd.Timestamp('2024-09-01',tz='UTC'):rows.append({'decision':t[j].isoformat(),'exit':exit_t[j].isoformat(),'horizon':h,'flow':float(f.flow[j]),'activity_ratio':float(f.activity_ratio[j]),'return_bps':float(ret[j])})
  if h==15:
   mask=((t>=pd.Timestamp('2024-09-01',tz='UTC'))&(exit_t<pd.Timestamp('2024-10-01',tz='UTC'))).to_numpy();rule=(f.flow.to_numpy()>.2)&(f.activity_ratio.to_numpy()>1.5);paper=[]
   for cost in [6,12,20]:
    pred=np.where(rule[mask],1.,0.);r=daily(t[mask].reset_index(drop=True),ret[mask],pred,h,.5,cost,'2024-09-01','2024-09-30');paper.append({'cost_bps':cost,'trades':int(rule[mask].sum()),'active_days':int((r!=0).sum()),'positive_days':int((r>0).sum()),'total_bps':float(r.sum()),'mean_bps_day':float(r.mean()),'day_bootstrap_95_ci':interval(r,rng)})
 result={'spec':SPEC,'sources':sources,'rows':len(d),'hypothesis_comparisons':records,'fixed_rule_evaluation':paper,'qualified':False,'orders_enabled':False,'primary_interaction_test_count':1,'secondary_interaction_test_count':2,'notes':['Intervals are nominal, not multiplicity-adjusted; exploratory secondary horizons.','No September tuning or model selection.','No ML model trained here: test information content before increasing model complexity.']}
 (out/'RESULTS.json').write_text(json.dumps(result,indent=2)+'\n');pd.DataFrame(rows).to_csv(out/'evaluation_observations.csv.gz',index=False);print(json.dumps({'primary_evaluation':[r for r in records if r['period']=='evaluation' and r['horizon']==15],'paper':paper},indent=2))
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--data',type=Path,default=Path('data/raw/long_horizon'));p.add_argument('--out',type=Path,default=Path('docs/flow_activity_hypothesis'));a=p.parse_args();study(a.data,a.out)
