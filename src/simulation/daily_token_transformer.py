"""Compact causal market-token learner; development comparison, never live promotion."""
import copy,csv,hashlib,json,time
from pathlib import Path
import numpy as np
import torch
from torch import nn
from sklearn.linear_model import LogisticRegression
from .crossasset_daily_research import load,portfolio
CONTEXT=16
TRAIN_CUT=int(np.datetime64('2024-10-01','ns').astype(np.int64))
VAL_CUT=int(np.datetime64('2024-12-31','ns').astype(np.int64))

class TokenTransformer(nn.Module):
    def __init__(self,fields=40,width=64,context=CONTEXT,classes=9):
        super().__init__();self.fields=fields;self.embed=nn.Embedding(fields*18,8);self.frame=nn.Linear(fields*8,width);self.position=nn.Embedding(context,width)
        layer=nn.TransformerEncoderLayer(width,4,128,.1,batch_first=True)
        self.encoder=nn.TransformerEncoder(layer,2,enable_nested_tensor=False);self.next_head=nn.Linear(width,fields*18);self.return_head=nn.Linear(width,classes)
        def initialize(m):
            if isinstance(m,(nn.Linear,nn.Embedding)):
                nn.init.xavier_uniform_(m.weight)
                if getattr(m,'bias',None) is not None:nn.init.zeros_(m.bias)
            if isinstance(m,nn.MultiheadAttention):
                nn.init.xavier_uniform_(m.in_proj_weight)
                if m.in_proj_bias is not None:nn.init.zeros_(m.in_proj_bias)
        self.apply(initialize)
    def hidden(self,x):
        b,l,f=x.shape;h=self.frame(self.embed(x).reshape(b,l,-1))+self.position(torch.arange(l,device=x.device))[None]
        mask=torch.ones(l,l,dtype=torch.bool,device=x.device).triu(1)
        return self.encoder(h,mask=mask,is_causal=True)
    def forward(self,x):return self.return_head(self.hidden(x)[:,-1])
    def language_logits(self,x):return self.next_head(self.hidden(x)).reshape(*x.shape,18)

def tokenize(values,train_mask):
    tr=values[train_mask];cuts=np.quantile(tr,np.arange(1,16)/16,axis=0).T;lo=tr.min(0);hi=tr.max(0);buckets=np.empty(values.shape,dtype=np.int64)
    for f in range(values.shape[1]):
        buckets[:,f]=1+np.searchsorted(cuts[f],values[:,f],side='right');buckets[values[:,f]<lo[f],f]=0;buckets[values[:,f]>hi[f],f]=17
    return buckets+18*np.arange(values.shape[1]),buckets,dict(cuts=cuts.tolist(),lower=lo.tolist(),upper=hi.tolist())

def probabilities(logits,temperature=1):
    z=np.asarray(logits)/temperature;z=z-z.max(1,keepdims=True);p=np.exp(z);return p/p.sum(1,keepdims=True)

def log_loss(p,c):return float(-np.mean(np.log(np.maximum(p[np.arange(len(c)),c],1e-12))))
def calibrate(logits,targets):
    losses={str(t):log_loss(probabilities(logits,t),targets) for t in (.5,1,2,4)}
    t=min((.5,1,2,4),key=lambda x:losses[str(x)]);return t,losses

def logits_for(model,x):
    model.eval()
    with torch.no_grad():return np.concatenate([model(torch.as_tensor(x[k:k+128],dtype=torch.long)).numpy() for k in range(0,len(x),128)])

def train_one(seed,x,lm_targets,pre_mask,classes,tr_mask,val_mask,pretrain=True):
    torch.manual_seed(seed);model=TokenTransformer();rng=np.random.default_rng(seed);trace=[];optimizer=torch.optim.AdamW(model.parameters(),lr=.001,weight_decay=.01)
    if pretrain:
        ids=np.flatnonzero(pre_mask)
        for epoch in range(10):
            model.train();total=0.;count=0
            for batch in np.array_split(rng.permutation(ids),int(np.ceil(len(ids)/64))):
                optimizer.zero_grad();z=model.language_logits(torch.as_tensor(x[batch],dtype=torch.long));target=torch.as_tensor(lm_targets[batch],dtype=torch.long);loss=nn.functional.cross_entropy(z.reshape(-1,18),target.reshape(-1));loss.backward();nn.utils.clip_grad_norm_(model.parameters(),1);optimizer.step();total+=float(loss.detach())*len(batch);count+=len(batch)
            trace.append(total/count)
    torch.manual_seed(seed+1000);rng=np.random.default_rng(seed+1000)
    optimizer=torch.optim.AdamW(model.parameters(),lr=.001,weight_decay=.01);ids=np.flatnonzero(tr_mask);best=None;best_loss=np.inf;fine=[]
    for epoch in range(30):
        model.train();total=0.;count=0
        for batch in np.array_split(rng.permutation(ids),int(np.ceil(len(ids)/64))):
            optimizer.zero_grad();z=model(torch.as_tensor(x[batch],dtype=torch.long));loss=nn.functional.cross_entropy(z,torch.as_tensor(classes[batch],dtype=torch.long));loss.backward();nn.utils.clip_grad_norm_(model.parameters(),1);optimizer.step();total+=float(loss.detach())*len(batch);count+=len(batch)
        logits=logits_for(model,x[val_mask]);vl=log_loss(probabilities(logits),classes[val_mask]);fine.append(dict(epoch=epoch+1,train_loss=total/count,validation_loss=vl))
        if vl<best_loss:best_loss=vl;best=copy.deepcopy(model.state_dict());best_epoch=epoch+1
    model.load_state_dict(best);t,losses=calibrate(logits_for(model,x[val_mask]),classes[val_mask]);return model,dict(seed=seed,pretrained=pretrain,pretraining_loss=trace,fine_tuning=fine,best_epoch=best_epoch,temperature=t,validation_temperature_losses=losses,parameters=sum(p.numel() for p in model.parameters()),fine_tuning_random_seed=seed+1000)

def onehot(tokens):
    buckets=tokens%18
    return np.eye(18,dtype=np.float32)[buckets].reshape(len(tokens),-1)

def metrics(p,y,c,means,returns):
    pred=p@means;truth=np.eye(len(means))[c];costs={}
    for cost in (5,10,25):
        q=portfolio(pred,returns,cost);q.pop('daily_returns');costs[str(cost)]=q
    return dict(log_loss=log_loss(p,c),multiclass_brier=float(np.mean(np.sum((p-truth)**2,axis=1))),return_mse=float(np.mean((pred-y)**2)),zero_return_mse=float(np.mean(y*y)),forecast_range_bps=[float(pred.min()),float(pred.max())],cost_per_side_bps=costs)

def run(root):
    start=time.monotonic();torch.set_num_threads(2);torch.use_deterministic_algorithms(True);root=Path(root);dates,ns,indices,lagged,y,opens=load(root)
    columns=np.array([a*28+f for a in range(10) for f in range(4)]);values=lagged[:,columns];tokens,buckets,tok=tokenize(values,ns[indices+1]<=TRAIN_CUT)
    k=np.arange(CONTEXT-1,len(indices));ix=indices[k];x=np.array([tokens[j-CONTEXT+1:j+1] for j in k]);lm=np.array([buckets[np.minimum(np.arange(j-CONTEXT+2,j+2),len(buckets)-1)] for j in k]);lm[-1,-1]=-100;target=y[k];returns=opens[ix+3]/opens[ix+2]-1
    tr=ns[ix+3]<=TRAIN_CUT;val=(ns[ix+1]>TRAIN_CUT)&(ns[ix+3]<=VAL_CUT);pre=ns[ix+2]<=TRAIN_CUT;ev=np.array(['2025-01-01'<=dates[i+2]<='2026-08-30' for i in ix]);cuts=np.quantile(target[tr],np.arange(1,9)/9);classes=np.searchsorted(cuts,target,side='right');means=np.array([target[tr][classes[tr]==c].mean() for c in range(9)])
    if not (tr.sum()>100 and val.sum()>20 and ev.sum()>100):raise ValueError('Insufficient chronological stages')
    assert ns[ix[tr]+3].max()<=TRAIN_CUT and ns[ix[pre]+2].max()<=TRAIN_CUT and ns[ix[val]+1].min()>TRAIN_CUT and ns[ix[val]+3].max()<=ns[ix[ev][0]+1]
    out=root/'docs/market_tokens/daily_transformer';out.mkdir(parents=True,exist_ok=True);prob={};reports={};trained=[]
    for seed in (91,92,93):
        model,info=train_one(seed,x,lm,pre,classes,tr,val,True);p=probabilities(logits_for(model,x[ev]),info['temperature']);trained.append(p);reports['pretrained_'+str(seed)]=info;prob['pretrained_'+str(seed)]=p
        np.savez_compressed(out/f'pretrained_{seed}_weights.npz',**{key:v.detach().numpy() for key,v in model.state_dict().items()})
        print('Completed pretrained seed',seed,flush=True)
    prob['pretrained_ensemble']=np.mean(trained,axis=0)
    model,info=train_one(91,x,lm,pre,classes,tr,val,False);reports['without_pretraining']=info;prob['without_pretraining']=probabilities(logits_for(model,x[ev]),info['temperature']);np.savez_compressed(out/'without_pretraining_weights.npz',**{key:v.detach().numpy() for key,v in model.state_dict().items()})
    last=onehot(x[:,-1]);baseline=LogisticRegression(C=.1,max_iter=2000).fit(last[tr],classes[tr]);t,cal=calibrate(baseline.decision_function(last[val]),classes[val]);prob['last_frame_logistic']=probabilities(baseline.decision_function(last[ev]),t);reports['last_frame_logistic']=dict(temperature=t,validation_temperature_losses=cal)
    prior=np.bincount(classes[tr],minlength=9)/tr.sum();prob['training_prior']=np.tile(prior,(ev.sum(),1));scores={name:metrics(p,target[ev],classes[ev],means,returns[ev]) for name,p in prob.items()}
    bh={}
    for cost in (5,10,25):q=portfolio(np.full(ev.sum(),100),returns[ev],cost);q.pop('daily_returns');bh[str(cost)]=q
    result=dict(status='exploratory_daily_token_transformer_comparison',qualified=False,orders_enabled=False,scope='Daily crossasset states, not multi-year intraday order-book events',training_examples=int(tr.sum()),pretraining_examples=int(pre.sum()),validation_examples=int(val.sum()),evaluation_days=int(ev.sum()),context_days=CONTEXT,fields=40,vocabulary=720,training_cutoff_ns=TRAIN_CUT,validation_cutoff_ns=VAL_CUT,first_execution=dates[ix[ev][0]+2],last_execution=dates[ix[ev][-1]+2],max_training_label_available_ns=int(ns[ix[tr]+3].max()),max_validation_label_available_ns=int(ns[ix[val]+3].max()),first_evaluation_observation_ns=int(ns[ix[ev][0]+1]),class_cuts_bps=cuts.tolist(),class_means_bps=means.tolist(),training_class_prior=prior.tolist(),tokenizer=tok,range_exceedance_eval_frames=int(np.sum(((buckets[k[ev]]==0)|(buckets[k[ev]]==17)).any(1))),range_exceedance_eval_contexts=int(np.sum((((x[ev]%18)==0)|((x[ev]%18)==17)).any(axis=(1,2)))),first_validation_observation_ns=int(ns[ix[val][0]+1]),models=reports,evaluation=scores,buy_and_hold=bh,cash_net_return_pct=0,elapsed_seconds=time.monotonic()-start,torch_version=torch.__version__,source_audit_sha256=hashlib.sha256((root/'docs/crossasset_daily/DATA_AUDIT.json').read_bytes()).hexdigest(),limits=['Periods already inspected; exploratory model and validation-selected checkpoints/calibration, not untouched validation.','Compact transformer trained from scratch on a small daily corpus, not pretrained ChatGPT/Chronos or a financial foundation model.','Contexts overlap; targets are daily nonoverlapping intervals. No claim of independent context counts.','Fixed initial train/validation and frozen evaluation weights; unlike earlier rolling regression benchmark. Compare only equal-training baselines here.','Range flags are diagnostic, no retrospective exclusion. Class-mean expected return is approximate, not a calibrated continuous distribution.','Daily ideal open fills with assumed fees omit observed spread, impact, size and stablecoin risk. No live qualification.'])
    (out/'RESULTS.json').write_text(json.dumps(result,indent=2)+'\n')
    with (out/'PREDICTIONS.csv').open('w') as f:
        names=list(prob);w=csv.writer(f);w.writerow(['execution_date','target_available_ns','target_log_return_bps','target_simple_return']+names)
        pp={name:p@means for name,p in prob.items()}
        for row,(i,tar,ret) in enumerate(zip(ix[ev],target[ev],returns[ev])):w.writerow([dates[i+2],int(ns[i+3]),float(tar),float(ret)]+[float(pp[name][row]) for name in names])
    print(json.dumps(dict(training=int(tr.sum()),validation=int(val.sum()),evaluation=int(ev.sum()),elapsed_seconds=result['elapsed_seconds'],scores={n:dict(log_loss=z['log_loss'],net_25bps=z['cost_per_side_bps']['25']['net_return_pct']) for n,z in scores.items()}),indent=2));return result
if __name__=='__main__':
    import sys
    run(sys.argv[1])
