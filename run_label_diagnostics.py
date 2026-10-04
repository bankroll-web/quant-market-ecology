"""Replay all attempts without fitting any predictor; selection diagnostics."""
import json,hashlib
from pathlib import Path
import numpy as np
import pandas as pd
from receipt_tokens import load_receipt_hours
from receipt_move_benchmark import receipt_segments,ranges
from market_label_validation import triple_barrier
from censoring_report import censoring_report,wilson_interval
from sample_uniqueness import average_uniqueness,sparse_sample

def run():
 out=Path('docs/label_diagnostics');out.mkdir(parents=True,exist_ok=True)
 hours,sources=load_receipt_hours(Path('.'),Path('../upload'));full=pd.concat(hours,ignore_index=True);segment,valid,_=receipt_segments(full);times=full.decision_receipt_ns.to_numpy(np.int64);lookup={};books=[]
 for h in full.hour.unique():
  p=Path(f'data/processed/mechanics_study_states/BTCUSDT_orderbook_{h}_observed_changes.csv');b=pd.read_csv(p);assert not b.received_time_ns.duplicated().any();books.append({'path':str(p),'sha256':hashlib.sha256(p.read_bytes()).hexdigest()})
  for r in b.itertuples():lookup[h,int(r.received_time_ns)]=(r.post_best_bid,r.post_best_ask,r.post_mid)
 records=[]
 for a,b in ranges(segment):
  quotes=[]
  for i in range(a,b):
   q=lookup[full.hour.iloc[i],int(times[i])];assert np.isclose(q[2],full.mid_t1.iloc[i],rtol=0,atol=1e-8)
   quotes.append(dict(time_ns=int(times[i]),bid=q[0],ask=q[1],segment=int(segment[i])))
  qt=np.array([q['time_ns'] for q in quotes],dtype=np.int64);returns=10000*np.diff(np.log(full.mid_t1.to_numpy(float)[a:b]));last=-10**30
  for j in range(20,len(quotes)):
   t=int(qt[j])
   if t-last<1_000_000_000:continue
   last=t;end=int(np.searchsorted(qt,t+1_250_000_000,side='right'));r=triple_barrier(quotes[j:end],t,t+1_000_000_000,1,1,latency_ns=50_000_000,max_gap_ns=250_000_000)
   r.update(decision_ns=t,vol_bps=float(np.std(returns[j-20:j],ddof=0)),segment=int(segment[j+a]),hour=str(full.hour.iloc[j+a]),row=j+a,segment_last_receipt_ns=int(qt[-1]),status='labeled' if r['status']=='observed' else 'censored');records.append(r)
 attempts=pd.DataFrame(records);survivors=attempts[attempts.status=='labeled'].copy();old=pd.read_csv('docs/quote_barrier_benchmark/labels.csv.gz');assert len(old)==len(survivors);assert old.event_start_ns.tolist()==survivors.decision_ns.tolist();assert old.label.tolist()==survivors.label.tolist()
 # Preserve integer nanoseconds: a censored row's absent endpoint must not force float timestamps.
 for c in ['label_available_ns','outcome_ns','entry_ns','event_end_ns']:attempts[c]=pd.array([r.get(c) for r in records],dtype='Int64')
 survivors=attempts[attempts.status=='labeled'].copy()
 rep=censoring_report(attempts);tables={}
 for k,v in rep.items():
  if isinstance(v,pd.DataFrame):
   v=v.copy()
   if 'group' in v:v['group']=v['group'].astype(str)
   tables[k]=v.to_dict('records')
 result={k:v for k,v in rep.items() if not isinstance(v,pd.DataFrame)};result.update(tables)
 starts=np.array([int(r['decision_ns']) for r in records if r['status']=='labeled'],dtype=np.int64);ends=np.array([int(r['label_available_ns']) for r in records if r['status']=='labeled'],dtype=np.int64)
 # Closed purge boundaries become half-open [start,end+1) for overlap code.
 u=average_uniqueness(starts,ends+1);keep=sparse_sample(starts,ends+1);survivors['uniqueness']=u;survivors['weight_normalized']=u*len(u)/u.sum();survivors['sparse_selected']=False;survivors.iloc[keep,survivors.columns.get_loc('sparse_selected')]=True
 longest=0
 for _,g in attempts.groupby('segment'):
  cur=0
  for flag in (g.status!='labeled'):
   cur=cur+1 if flag else 0;longest=max(longest,cur)
 extra=[]
 for name,mask in [('zero_past_volatility',attempts.vol_bps==0),('positive_past_volatility',attempts.vol_bps>0)]:
  n=int(mask.sum());k=int((attempts.loc[mask,'status']!='labeled').sum());extra.append(dict(group=name,attempts=n,censored=k,rate=k/n if n else None,nominal_wilson_95_ci=wilson_interval(k,n)))
 result['zero_vs_positive_volatility']=extra
 result['censored_without_segment_deadline_coverage']=int(((attempts.status!='labeled') & (attempts.segment_last_receipt_ns<attempts.decision_ns+1_000_000_000)).sum())
 result['volatility_quantile_trend_assessable']=len(rep['by_volatility'])>=2
 result.update(uniqueness={'labels':len(u),'mean':float(u.mean()),'minimum':float(u.min()),'sum_overlap_equivalent_mass':float(u.sum()),'nonoverlapping_subset':len(keep),'statistical_independence_claim':False,'convention':'closed receipt intervals represented as [decision,label_available+1ns)'},longest_failure_run_within_segment=longest,input_rows=len(full),valid_rows=int(valid.sum()),trade_sources=sources,book_sources=books,qualified=False,orders_enabled=False,limits=['Attempts start only after 20 valid segment events and use one-second sampling. Invalid rows, warm-up rows and absent recordings are not label attempts; report is not feed uptime.','Past volatility is standard deviation of 20 observed midpoint log changes ending at decision, not clock-time volatility or future volatility.','Diagnostic quantile buckets use full sample, never reused as model bins.','Wilson intervals and their separation flag are nominal; serial dependence and multiple comparisons are not adjusted.','Raw consecutive-failure runs may bridge noncontiguous recordings; segment-local run reported separately.','Censoring may reflect fixed horizon and record boundaries, not a broken live feed.','Uniqueness sum is overlap-equivalent mass, not a statistical effective sample size; sparse labels can remain dependent.','No models fitted or live changes performed.'])
 attempts.to_csv(out/'attempts.csv.gz',index=False);survivors.to_csv(out/'uniqueness.csv.gz',index=False);(out/'RESULTS.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps({k:result[k] for k in ['attempts','overall_censor_rate','by_volatility','flags','uniqueness','longest_failure_run_within_segment']},indent=2))
if __name__=='__main__':run()
