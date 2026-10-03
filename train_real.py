"""Fixed-budget D09 token comparison. Event-time development only, never live qualification."""
import argparse,hashlib,json
from pathlib import Path
import numpy as np
import pandas as pd
import torch
from torch import nn
from tokenizer_v1 import load_hours,MarketTokenizer,SPEC
FIELDS=list(SPEC);L=16;H=10;QS=np.array([.1,.25,.5,.75,.9])
class Model(nn.Module):
    def __init__(self,vocab):
        super().__init__();self.emb=nn.ModuleList([nn.Embedding(vocab[f],32) for f in FIELDS]);self.pos=nn.Embedding(L,32);self.encoder=nn.TransformerEncoder(nn.TransformerEncoderLayer(32,4,64,.1,batch_first=True),1,enable_nested_tensor=False);self.heads=nn.ModuleList([nn.Linear(32,vocab[f]) for f in FIELDS]);self.q=nn.Linear(32,5);self.flow=nn.Linear(32,1);self.vol=nn.Linear(32,1)
    def forward(self,x):
        h=sum(e(x[:,:,i]) for i,e in enumerate(self.emb))+self.pos(torch.arange(L))[None];h=self.encoder(h,mask=torch.ones(L,L,dtype=torch.bool).triu(1))[:,-1];z=self.q(h);q=torch.cat([z[:,:1],z[:,:1]+nn.functional.softplus(z[:,1:]).cumsum(1)],1);return [a(h) for a in self.heads],q,self.flow(h).tanh().squeeze(1),self.vol(h).squeeze(1)
def samples(df,tokens):
    a=tokens.values;ep=df['episode_id'].values;mid=df['mid_t1'].values;times=df['t1_event_time_ms'].values;index=df['interval_index'].values;signed=df['signed_flow_qty'].values;total=df['total_flow_qty'].values;out=[]
    for j in range(L-1,len(df)-H,H):
        lo=j-L+1;hi=j+H
        if len(set(ep[lo:hi+1]))!=1 or np.any(np.diff(times[lo:hi+1])<=0) or np.any(np.diff(index[lo:hi+1])!=1):continue
        qty=total[j+1:hi+1].sum();out.append((a[lo:j+1],a[j+1],10000*np.log(mid[hi]/mid[j]),np.nan if qty<=0 else signed[j+1:hi+1].sum()/qty,10000*np.mean(np.abs(np.diff(np.log(mid[j:hi+1])))),times[j],times[hi]))
    if not out:raise ValueError('No contiguous episode examples')
    return [np.array(x) for x in zip(*out)]
def main(root):
    root=Path(root);torch.set_num_threads(2);torch.manual_seed(91);rng=np.random.default_rng(91);hours=load_hours(root)
    if len(hours)!=5:raise ValueError('Expected fixed five-hour D09 comparison')
    train=pd.concat(hours[:3],ignore_index=True);test=pd.concat(hours[3:],ignore_index=True)
    for d in (train,test):d['episode_id']=d['hour']+'_'+d['episode_id'].astype(str)
    tk=MarketTokenizer().fit(train);tr,_=tk.transform(train);te,_=tk.transform(test);a=samples(train,tr);b=samples(test,te);x,y,ret,flow,vol,dec,end=a;xx,yy,rr,ff,vv,dd,ee=b;rs=max(ret.std(),1e-6);vs=max(vol.std(),1e-6);m=Model(tk.vocab);opt=torch.optim.AdamW(m.parameters(),lr=.001);qs=torch.tensor(QS,dtype=torch.float32);losses=[]
    for epoch in range(5):
        m.train();track=[]
        for ids in np.array_split(rng.permutation(len(x)),int(np.ceil(len(x)/128))):
            fields,q,f,v=m(torch.tensor(x[ids]));r=torch.tensor(ret[ids]/rs,dtype=torch.float32);err=r[:,None]-q;fm=np.isfinite(flow[ids]);loss=sum(nn.functional.cross_entropy(z,torch.tensor(y[ids,i])) for i,z in enumerate(fields))/12+torch.maximum(qs*err,(qs-1)*err).mean()+.3*((v-torch.tensor(vol[ids]/vs,dtype=torch.float32))**2).mean()
            if fm.any():loss=loss+.3*((f[fm]-torch.tensor(flow[ids][fm],dtype=torch.float32))**2).mean()
            opt.zero_grad();loss.backward();nn.utils.clip_grad_norm_(m.parameters(),1);opt.step();track.append(float(loss.detach()))
        losses.append(float(np.mean(track)));print('epoch',epoch+1,losses[-1],flush=True)
    m.eval();pp=[[] for f in FIELDS];qp=[];fp=[];vp=[]
    with torch.no_grad():
        for j in range(0,len(xx),256):
            z,q,f,v=m(torch.tensor(xx[j:j+256]));qp.extend((q*rs).numpy());fp.extend(f.numpy());vp.extend((v*vs).numpy())
            for i,zz in enumerate(z):pp[i].extend(zz.softmax(1).numpy())
    scores={}
    for i,f in enumerate(FIELDS):
        size=tk.vocab[f];joint=np.ones((size,size));np.add.at(joint,(x[:,-1,i],y[:,i]),1);cond=joint/joint.sum(1,keepdims=True);prior=np.bincount(y[:,i],minlength=size)+1;prior=prior/prior.sum();p=np.array(pp[i]);truth=yy[:,i];scores[f]={'transformer_bits':float(-np.log2(np.maximum(p[np.arange(len(truth)),truth],1e-12)).mean()),'bigram_bits':float(-np.log2(cond[xx[:,-1,i],truth]).mean()),'prior_bits':float(-np.log2(prior[truth]).mean())}
    qp=np.array(qp);base=np.quantile(ret,QS);err=rr[:,None]-qp;be=rr[:,None]-base;fm=np.isfinite(ff)
    result={'status':'D09_12_field_development_comparison','qualified':False,'orders_enabled':False,'train_events':len(train),'test_events':len(test),'training_samples':len(x),'evaluation_samples':len(xx),'context_events':L,'target_events':H,'epochs':5,'seed':91,'training_losses':losses,'field_scores':scores,'return_pinball_bps':float(np.maximum(QS*err,(QS-1)*err).mean()),'baseline_return_pinball_bps':float(np.maximum(QS*be,(QS-1)*be).mean()),'coverage_80':float(np.mean((rr>=qp[:,0])&(rr<=qp[:,-1]))),'flow_mse':float(np.mean((np.array(fp)[fm]-ff[fm])**2)),'baseline_flow_mse':float(np.mean((np.nanmean(flow)-ff[fm])**2)),'flow_evaluation_samples':int(fm.sum()),'vol_mse':float(np.mean((np.array(vp)-vv)**2)),'baseline_vol_mse':float(np.mean((vol.mean()-vv)**2)),'source_sha256':{p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted((root/'data/frozen').glob('2026-*d09*.csv'))},'limits':['Event-time D09 tapes have no receipt availability timestamps. No live timing qualification.','All five recording hours already examined. Development comparison, not untouched evidence.','Ten-event targets have variable elapsed time; contexts overlap. No PnL or cost replay.','Fixed five epochs; no evaluation checkpoint selection. Missing no-trade flow labels excluded rather than set to zero.','Hard-coded 0.1 tick inherited from uploaded tokenizer; mid rounding can discard half-tick moves. Reset/sweep attribution not established.']}
    out=root/'docs/market_tokens/d09_trial';out.mkdir(parents=True,exist_ok=True);(out/'RESULTS.json').write_text(json.dumps(result,indent=2)+'\n');np.savez_compressed(out/'WEIGHTS.npz',**{k:v.detach().numpy() for k,v in m.state_dict().items()});print(json.dumps({k:v for k,v in result.items() if k not in ('source_sha256','limits','field_scores')},indent=2))
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--repo',default='.');a=p.parse_args();main(a.repo)
