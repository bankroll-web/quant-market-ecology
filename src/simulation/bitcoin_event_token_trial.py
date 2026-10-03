"""Observed book-change token integration; unknown identities and trade flow stay missing."""
import bisect,csv,hashlib,json,math
from pathlib import Path
import numpy as np
import torch
from torch import nn
from .observed_ecology_environment import load,examples
from .six_field_tokens import QuantileCodec,SixFieldTokenizer

class BookTokenModel(nn.Module):
    def __init__(self,vocabulary):
        super().__init__();self.embedding=nn.Embedding(vocabulary,32);self.position=nn.Embedding(8,32);self.encoder=nn.TransformerEncoder(nn.TransformerEncoderLayer(32,4,64,.1,batch_first=True),1,enable_nested_tensor=False);self.quantiles=nn.Linear(32,5);self.vol=nn.Linear(32,1)
    def forward(self,x):
        h=self.embedding(x).sum(2)+self.position(torch.arange(x.shape[1]))[None];mask=torch.ones(x.shape[1],x.shape[1],dtype=torch.bool).triu(1);h=self.encoder(h,mask=mask)[:,-1];z=self.quantiles(h);q=torch.cat([z[:,:1],z[:,:1]+torch.cumsum(nn.functional.softplus(z[:,1:]),1)],1);return q,self.vol(h).squeeze(1)

def run(root):
    root=Path(root);torch.set_num_threads(2);torch.manual_seed(91);rng=np.random.default_rng(91)
    paths=sorted((root/'data/processed/mechanics_study_states').glob('*_observed_changes.csv'))+sorted((root/'data/processed/mechanics_replication_states').glob('*_observed_changes.csv'));paths=sorted(paths);first=next(p for p in paths if '2026-05-25_00' in p.name);paths.remove(first);paths.insert(0,first)
    data=[];raws=[]
    for path in paths:
        r=load(path);raws.append(r);data.append(examples(r))
    cutoff=data[0][len(data[0])//2]['decision_ns'];r=raws[0]
    def quantity(row):return sum(row[k] for k in ('bid_add_qty','bid_remove_qty','ask_add_qty','ask_remove_qty'))
    trainrows=[j for j in range(1,len(r)) if r[j]['received_time_ns']<=cutoff and r[j]['episode']==r[j-1]['episode'] and 0<r[j]['received_time_ns']-r[j-1]['received_time_ns']<=250_000_000]
    times=np.array([r[j]['received_time_ns'] for j in trainrows]);sizes=np.array([np.log1p(quantity(r[j])) for j in trainrows]);gaps=np.array([np.log1p((r[j]['received_time_ns']-r[j-1]['received_time_ns'])/1e9) for j in trainrows]);sc=QuantileCodec(32).fit(sizes,times,cutoff);gc=QuantileCodec(32).fit(gaps,times,cutoff);codec=SixFieldTokenizer(sc,gc)
    groups=[]
    for rows,labels in zip(raws,data):
        times=[row['received_time_ns'] for row in rows];samples=[]
        for label in labels:
            t=label['decision_ns'];j=bisect.bisect_left(times,t);end=bisect.bisect_left(times,label['label']['target_end_ns']);start=j-7
            if start<1 or any(rows[k]['episode']!=rows[j]['episode'] or not 0<times[k]-times[k-1]<=250_000_000 or rows[k]['post_best_bid']>=rows[k]['post_best_ask'] or rows[k]['event_time_ms']*10**6>times[k] for k in range(start,end+1)):continue
            # IDs of a frozen initial codec can be used for training history; online availability is gated at cutoff or later.
            tokens=[codec.encode('book_change','unknown',None,quantity(rows[k]),(times[k]-times[k-1])/1e9,decision_ns=max(cutoff,times[k])) for k in range(start,j+1)]
            mids=np.array([rows[k]['post_mid'] for k in range(j,end+1)]);vol=10000*np.mean(np.abs(np.diff(np.log(mids))))
            samples.append(dict(decision_ns=t,label_ns=label['label']['label_available_ns'],tokens=tokens,ret=label['label']['return_bps'],vol=vol))
        groups.append(samples)
    train=[s for s in groups[0] if s['label_ns']<=cutoff];evaluation=[s for group in groups for s in group if s['decision_ns']>cutoff]
    if len(train)<100 or len(evaluation)<100:raise ValueError('Insufficient eligible samples')
    x=torch.tensor(np.array([s['tokens'] for s in train]));y=torch.tensor([s['ret'] for s in train]);v=torch.tensor([s['vol'] for s in train]);rscale=max(float(y.std()),.01);vscale=max(float(v.std()),.01);model=BookTokenModel(codec.vocabulary_size);opt=torch.optim.AdamW(model.parameters(),lr=.001);qs=torch.tensor([.1,.25,.5,.75,.9]);losses=[]
    for epoch in range(5):
        model.train();trace=[]
        for ids in np.array_split(rng.permutation(len(train)),int(np.ceil(len(train)/64))):
            q,p=model(x[ids]);err=y[ids,None]/rscale-q;loss=torch.maximum(qs*err,(qs-1)*err).mean()+.3*((p-v[ids]/vscale)**2).mean();opt.zero_grad();loss.backward();nn.utils.clip_grad_norm_(model.parameters(),1);opt.step();trace.append(float(loss.detach()))
        losses.append(float(np.mean(trace)))
    model.eval();pred=[];volpred=[]
    with torch.no_grad():
        for start in range(0,len(evaluation),256):
            z=torch.tensor(np.array([s['tokens'] for s in evaluation[start:start+256]]));q,p=model(z);pred.extend((q*rscale).numpy());volpred.extend((p*vscale).numpy())
    pred=np.array(pred);truth=np.array([s['ret'] for s in evaluation]);voltruth=np.array([s['vol'] for s in evaluation]);base=np.quantile(y.numpy(),qs.numpy());err=truth[:,None]-pred;be=truth[:,None]-base
    result={'status':'first_real_book_change_six_field_trial','qualified':False,'orders_enabled':False,'training_cutoff_ns':cutoff,'training_samples':len(train),'evaluation_samples':len(evaluation),'training_raw_codec_frames':len(trainrows),'vocabulary_size':codec.vocabulary_size,'context_receipts':8,'epochs':5,'seed':91,'training_losses':losses,'pinball_bps':float(np.maximum(qs.numpy()*err,(qs.numpy()-1)*err).mean()),'baseline_pinball_bps':float(np.maximum(qs.numpy()*be,(qs.numpy()-1)*be).mean()),'coverage_80':float(np.mean((truth>=pred[:,0])&(truth<=pred[:,-1]))),'volatility_mse':float(np.mean((np.array(volpred)-voltruth)**2)),'baseline_volatility_mse':float(np.mean((float(v.mean())-voltruth)**2)),'flow_head_trained':False,'source_sha256':{p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in paths},'limits':['Eight discontinuous recorded hours already examined; development comparison, no untouched sample or profitability claim.','Book-change bundles, not individual add/cancel orders. Gross displayed quantity changes are not traded volume.','Level, side and participant are missing; tick metadata and synchronized trades unavailable in this adapter.','One-second targets use receipt sampling with up to 250ms lag; outcomes can overlap, sample counts are not independent.','No trade-flow target, multi-scale integration, rollouts, costs, fills or live promotion.','Five fixed epochs; evaluation not used for checkpoint selection. Initial frozen codec retrospectively encodes training context; online decisions strictly after cutoff.']}
    out=root/'docs/market_tokens/bitcoin_event_trial';out.mkdir(exist_ok=True);(out/'RESULTS.json').write_text(json.dumps(result,indent=2)+'\n');np.savez_compressed(out/'WEIGHTS.npz',**{k:t.detach().numpy() for k,t in model.state_dict().items()})
    preprocessing={'size':dict(cuts=sc.cuts.tolist(),centers=sc.centers.tolist(),lower=sc.lower,upper=sc.upper),'gap':dict(cuts=gc.cuts.tolist(),centers=gc.centers.tolist(),lower=gc.lower,upper=gc.upper),'return_scale':rscale,'vol_scale':vscale,'cutoff_ns':cutoff,'bins':32};(out/'PREPROCESSING.json').write_text(json.dumps(preprocessing,indent=2)+'\n')
    with (out/'PREDICTIONS.csv').open('w') as f:
        w=csv.writer(f);w.writerow(['decision_ns','label_ns','return_bps','vol_proxy_bps','q10','q25','q50','q75','q90','vol_forecast_bps'])
        for s,q,p in zip(evaluation,pred,volpred):w.writerow([s['decision_ns'],s['label_ns'],s['ret'],s['vol'],*q,p])
    print(json.dumps({k:v for k,v in result.items() if k not in ('limits','source_sha256')},indent=2));return result
if __name__=='__main__':
    import sys
    run(sys.argv[1])
