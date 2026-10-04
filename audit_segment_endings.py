"""Attribute censored attempts to observed segment endings; no gap repair."""
import json
from pathlib import Path
import numpy as np
import pandas as pd
from receipt_tokens import load_receipt_hours
from receipt_move_benchmark import receipt_segments,ranges,MAX_GAP_NS

def run():
 out=Path('docs/segment_endings');out.mkdir(parents=True,exist_ok=True)
 hours,sources=load_receipt_hours(Path('.'),Path('../upload'));d=pd.concat(hours,ignore_index=True);seg,valid,post_ok=receipt_segments(d);times=d.decision_receipt_ns.to_numpy(np.int64);events=d.t1_event_time_ms.to_numpy(np.int64)*1_000_000;ends={};rows=[]
 for a,b in ranges(seg):
  i=b-1;j=b;causes=[]
  if j==len(d):causes=['recording_end']
  else:
   if d.hour.iloc[j]!=d.hour.iloc[i]:causes.append('recording_hour_boundary')
   if d.episode_id.iloc[j]!=d.episode_id.iloc[i]:causes.append('source_episode_boundary')
   if d.interval_index.iloc[j]!=d.interval_index.iloc[i]+1:causes.append('interval_index_discontinuity')
   if times[j]<=times[i]:causes.append('receipt_tie_or_reversal')
   elif times[j]-times[i]>MAX_GAP_NS:causes.append('receipt_gap_over_250ms')
   if not bool(d.receipt_valid.iloc[j]):causes.append('adapter_receipt_invalid')
   if times[j]<events[j]:causes.append('future_exchange_timestamp')
   elif times[j]-events[j]>MAX_GAP_NS:causes.append('next_event_age_over_250ms')
   if not post_ok[j]:causes.append('next_post_state_not_confirmable')
   for col in ['bid_depth5_t0','ask_depth5_t0']:
    x=float(d[col].iloc[j+1]) if j+1<len(d) else float('nan')
    if not np.isfinite(x) or x<=0:causes.append('next_post_depth_invalid');break
   x=float(d.obi5_t0.iloc[j+1]) if j+1<len(d) else float('nan')
   if not np.isfinite(x) or abs(x)>1:causes.append('next_post_imbalance_invalid')
   if not causes:causes=['other_validity_gate']
  r=dict(segment=int(seg[i]),hour=str(d.hour.iloc[i]),start_row=int(a),last_row=int(i),valid_events=b-a,duration_ms=float((times[i]-times[a])/1e6),end_ns=int(times[i]),causes=causes);ends[int(seg[i])]=r;rows.append(r)
 attempts=pd.read_csv('docs/label_diagnostics/attempts.csv.gz',dtype={'decision_ns':'int64','segment_last_receipt_ns':'int64'});c=attempts[attempts.status!='labeled'].copy();assert len(c)==1698;linked=[]
 for r in c.itertuples():
  e=ends[int(r.segment)];assert e['end_ns']==r.segment_last_receipt_ns
  linked.append(dict(decision_ns=int(r.decision_ns),segment=int(r.segment),reason=r.reason,vol_bps=float(r.vol_bps),remaining_segment_ms=float((e['end_ns']-r.decision_ns)/1e6),causes=e['causes']))
 counts={};exclusive={}
 for r in linked:
  exclusive[' + '.join(r['causes'])]=exclusive.get(' + '.join(r['causes']),0)+1
  for cause in r['causes']:counts[cause]=counts.get(cause,0)+1
 result=dict(segments=len(rows),censored_attempts=len(linked),cause_counts_nonexclusive=counts,cause_combinations=exclusive,segment_duration_ms_quantiles=np.quantile([r['duration_ms'] for r in rows],[0,.25,.5,.75,.9,1]).tolist(),trade_sources=sources,qualified=False,orders_enabled=False,limits=['Categories are observed timing/state gate failures, not proof of raw exchange update-ID loss.','Reasons overlap; nonexclusive counts cannot be summed.','Next post-state confirmation uses the following reconstructed row; this is an audit of existing preprocessing, not a relaxation or live repair.','Historical invalid sections cannot be replaced with synthetic observations.','No training or live-service modification.'])
 (out/'RESULTS.json').write_text(json.dumps(result,indent=2)+'\n');pd.DataFrame(rows).assign(causes=lambda x:x.causes.map(json.dumps)).to_csv(out/'segments.csv.gz',index=False);pd.DataFrame(linked).assign(causes=lambda x:x.causes.map(json.dumps)).to_csv(out/'censored_causes.csv.gz',index=False);print(json.dumps({k:v for k,v in result.items() if k not in ['trade_sources','limits']},indent=2))
if __name__=='__main__':run()
