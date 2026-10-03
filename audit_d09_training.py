from pathlib import Path
import json,hashlib,gzip,csv,io
import numpy as np
import pandas as pd
import torch
from tokenizer_v1 import load_hours,MarketTokenizer,SPEC,MID_EDGES,NTR_EDGES,TICK,QLEVELS
from train_real import Model,samples
import sys
root=Path(sys.argv[1]) if len(sys.argv)>1 else Path(__file__).resolve().parent;out=root/'docs/market_tokens/d09_trial';r=json.loads((out/'RESULTS.json').read_text());hours=load_hours(root);a=pd.concat(hours[:3],ignore_index=True);b=pd.concat(hours[3:],ignore_index=True)
for d in (a,b):d['episode_id']=d['hour']+'_'+d['episode_id'].astype(str)
tk=MarketTokenizer().fit(a);tr,_=tk.transform(a);te,_=tk.transform(b);train=samples(a,tr);test=samples(b,te);x,y,ret,flow,vol,dec,end=train;xx,yy,rr,ff,vv,dd,ee=test
assert end.max()<dd.min();rs=max(ret.std(),1e-6);vs=max(vol.std(),1e-6)
pre={'fields':list(SPEC),'vocab':tk.vocab,'binners':{f:{k:v.tolist() if isinstance(v,np.ndarray) else v for k,v in obj.__dict__.items()} for f,obj in tk.b.items()},'mid_edges':MID_EDGES.tolist(),'trade_count_edges':NTR_EDGES.tolist(),'tick_assumption':TICK,'quantile_levels':QLEVELS,'return_scale':rs,'vol_scale':vs,'latest_training_target_event_ms':int(end.max()),'first_evaluation_decision_event_ms':int(dd.min())};(out/'PREPROCESSING.json').write_text(json.dumps(pre,indent=2)+'\n')
torch.set_num_threads(2);m=Model(tk.vocab);w=np.load(out/'WEIGHTS.npz',allow_pickle=False);m.load_state_dict({k:torch.tensor(w[k]) for k in w.files});m.eval();records=[];mid_p=[]
with torch.no_grad():
 for j in range(0,len(xx),256):
  z,q,f,v=m(torch.tensor(xx[j:j+256]));q=(q*rs).numpy();f=f.numpy();v=(v*vs).numpy();mid_p.extend(z[list(SPEC).index('mid')].softmax(1).numpy())
  for k in range(len(q)):i=j+k;records.append([int(dd[i]),int(ee[i]),rr[i],ff[i],vv[i],*q[k],f[k],v[k]])
numeric=np.array([row[5:10] for row in records]);err=rr[:,None]-numeric;quantiles=np.array([.1,.25,.5,.75,.9]);score=float(np.maximum(quantiles*err,(quantiles-1)*err).mean());assert abs(score-r['return_pinball_bps'])<1e-7
with gzip.open(out/'PREDICTIONS.csv.gz','wt') as fp:
 writer=csv.writer(fp);writer.writerow(['decision_event_ms','target_event_ms','return_bps','signed_flow','vol_proxy_bps','q10','q25','q50','q75','q90','flow_forecast','vol_forecast']);writer.writerows(records)
i=list(SPEC).index('mid');truth=yy[:,i];mp=np.array(mid_p);counts=np.ones((tk.vocab['mid'],tk.vocab['mid']));np.add.at(counts,(x[:,-1,i],y[:,i]),1);conditional=counts/counts.sum(1,keepdims=True);moving=truth!=0
rare={'later_nonzero_mid_targets':int(moving.sum()),'later_zero_mid_targets':int((~moving).sum()),'moving_target_transformer_bits':float(-np.log2(np.maximum(mp[np.arange(len(truth))[moving],truth[moving]],1e-12)).mean()),'moving_target_bigram_bits':float(-np.log2(conditional[xx[moving,-1,i],truth[moving]]).mean()),'note':'Conditional diagnostic only; rare outcomes must not be selected by model forecasts or confused with unconditional performance.'}
(out/'RARE_MOVE_DIAGNOSTICS.json').write_text(json.dumps(rare,indent=2)+'\n')
audit={'rows':len(records),'saved_npz_loaded_without_pickle':True,'max_training_target_before_first_eval_decision':True,'max_training_target_event_ms':int(end.max()),'first_eval_decision_event_ms':int(dd.min()),'time_basis':'exchange event-time only; receipt-time qualification missing','artifacts':{p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in out.iterdir() if p.is_file() and p.name != "RUN_AUDIT.json"},'upload_sha256':{p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in [root/'tokenizer_v1.py',root/'ecology_arena.py']}};(out/'RUN_AUDIT.json').write_text(json.dumps(audit,indent=2)+'\n');print(rare)
