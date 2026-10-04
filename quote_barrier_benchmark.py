import json,hashlib
from pathlib import Path
import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.metrics import log_loss
from receipt_tokens import load_receipt_hours
from receipt_move_benchmark import receipt_segments,ranges,build_features,lag_features,MatchedTokenizer
from market_label_validation import triple_barrier,purged_walk_forward
SPEC=dict(version='quote-barrier-v1',horizon_ms=1000,latency_ms=50,profit_bps=1,loss_bps=1,fee_bps=0,max_gap_ms=250,spacing_ms=1000,context=4,scope='Five previously inspected hours; development only. Spread included, top-quote proxy, zero additional fees; no profit qualification.')
def run():
 out=Path('docs/quote_barrier_benchmark');out.mkdir(parents=True,exist_ok=True);(out/'SPEC.json').write_text(json.dumps(SPEC,indent=2)+'\n')
 hours,sources=load_receipt_hours(Path('.'),Path('../upload'));full=pd.concat(hours,ignore_index=True);segment,valid,_=receipt_segments(full);features=build_features(full,segment);raw=lag_features(features,segment);times=full.decision_receipt_ns.to_numpy(np.int64);lookup={};books=[]
 for h in full.hour.unique():
  path=Path(f'data/processed/mechanics_study_states/BTCUSDT_orderbook_{h}_observed_changes.csv');b=pd.read_csv(path);assert not b.received_time_ns.duplicated().any()
  books.append(dict(path=str(path),sha256=hashlib.sha256(path.read_bytes()).hexdigest()))
  for r in b.itertuples():lookup[h,int(r.received_time_ns)]=(r.post_best_bid,r.post_best_ask,r.post_mid)
 records=[];censored={}
 for a,b in ranges(segment):
  quotes=[]
  for i in range(a,b):
   q=lookup.get((full.hour.iloc[i],int(times[i])));assert q is not None and np.isclose(q[2],full.mid_t1.iloc[i],rtol=0,atol=1e-8),'Quote join mismatch'
   quotes.append(dict(time_ns=int(times[i]),bid=q[0],ask=q[1],segment=int(segment[i])))
  qt=np.array([q['time_ns'] for q in quotes],dtype=np.int64);last=-10**30
  for j in range(20,len(quotes)):
   t=int(qt[j])
   if t-last<1_000_000_000:continue
   last=t;end=int(np.searchsorted(qt,t+1_250_000_000,side='right'));r=triple_barrier(quotes[j:end],t,t+1_000_000_000,1,1,latency_ns=50_000_000,max_gap_ns=250_000_000)
   if r['status']!='observed':censored[r['reason']]=censored.get(r['reason'],0)+1;continue
   r.update(row=a+j,hour=str(full.hour.iloc[a+j]),feature_start_ns=int(times[a+j-3]));records.append(r)
 obs=pd.DataFrame(records);predictions=[];folds=[];fits=0;unique=list(full.hour.unique());events=[dict(start_ns=int(r.feature_start_ns),end_ns=int(r.label_available_ns)) for r in obs.itertuples()]
 for fold in range(1,len(unique)):
  te=np.flatnonzero(obs.hour.to_numpy()==unique[fold]).tolist()
  if not te:continue
  tr,te=purged_walk_forward(events,te,embargo_ns=1_000_000_000)
  if not tr:continue
  y=obs.label.to_numpy();train_rows=obs.row.to_numpy()[tr];test_rows=obs.row.to_numpy()[te];counts=np.bincount(y[tr]+1,minlength=3);prior=(counts+1)/(counts.sum()+3);base=np.tile(prior,(len(te),1));mask=np.zeros(len(full),bool);mask[train_rows]=True;tok=MatchedTokenizer().fit(features,mask);xx=lag_features(tok.transform(features),segment);(out/f'bins_fold_{fold}.json').write_text(json.dumps(tok.state()))
  for name,data in [('numeric',raw),('tokens',xx)]:
   if len(np.unique(y[tr]))<2:p=base.copy();trained=False
   else:
    m=HistGradientBoostingClassifier(max_iter=80,min_samples_leaf=40,max_leaf_nodes=15,l2_regularization=2,early_stopping=False,random_state=31).fit(data.iloc[train_rows],y[tr]);p=np.full((len(te),3),1e-12);p[:,m.classes_.astype(int)+1]=m.predict_proba(data.iloc[test_rows]);p/=p.sum(axis=1,keepdims=True);fits+=1;trained=True
   folds.append(dict(fold=fold,hour=str(unique[fold]),model=name,train=len(tr),test=len(te),trained=trained,log_loss=float(log_loss(y[te],p,labels=[-1,0,1])),baseline_log_loss=float(log_loss(y[te],base,labels=[-1,0,1]))))
   for k,i in enumerate(te):predictions.append(dict(fold=fold,model=name,decision_ns=int(obs.event_start_ns.iloc[i]),label=int(y[i]),p_loss=float(p[k,0]),p_time=float(p[k,1]),p_profit=float(p[k,2]),net_proxy_bps=float(obs.net_log_bps.iloc[i])))
 result=dict(spec=SPEC,input_rows=len(full),valid_rows=int(valid.sum()),observed_labels=len(obs),censored=censored,label_counts={str(k):int((obs.label==k).sum()) for k in [-1,0,1]},fits=fits,folds=folds,trade_sources=sources,book_sources=books,qualified=False,orders_enabled=False)
 (out/'RESULTS.json').write_text(json.dumps(result,indent=2)+'\n');obs.to_csv(out/'labels.csv.gz',index=False);pd.DataFrame(predictions).to_csv(out/'predictions.csv.gz',index=False);print(json.dumps({k:result[k] for k in ['observed_labels','censored','label_counts','fits','folds']},indent=2))
if __name__=='__main__':run()
