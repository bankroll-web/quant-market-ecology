"""River incremental learning on receipt-clock tokens; frozen development evaluation."""
import argparse,heapq,json,hashlib
from pathlib import Path
import numpy as np
import pandas as pd
import river
from river import linear_model,optim,drift
from receipt_tokens import load_receipt_hours,receipt_samples,POLICY
from tokenizer_v1 import MarketTokenizer,SPEC
FIELDS=list(SPEC)
def token_features(context):
    # Categorical IDs are never treated as an ordinal numerical scale.
    out={}
    for i,f in enumerate(FIELDS):
        values,counts=np.unique(context[:,i],return_counts=True)
        for value,count in zip(values,counts):out[f+'|frequency|'+str(value)]=float(count)/len(context)
        out[f+'|latest|'+str(context[-1,i])]=1.
    return out

def main(repo,upload):
    root=Path(repo);hours,audit=load_receipt_hours(root,upload)
    for df in hours:df['episode_id']=df['hour']+'_'+df['episode_id'].astype(str)
    # First recording is tokenizer warmup only, strictly before learning/evaluation.
    tk=MarketTokenizer().fit(hours[0].loc[hours[0]['receipt_valid']])
    train=pd.concat(hours[1:3],ignore_index=True);test=pd.concat(hours[3:],ignore_index=True)
    tr,_=tk.transform(train);te,_=tk.transform(test)
    a=receipt_samples(train,tr);b=receipt_samples(test,te)
    assert a[6].max()<b[5].min()
    names=['return','flow','vol'];models={n:linear_model.LinearRegression(optimizer=optim.SGD(.01),l2=.0001,clip_gradient=10) for n in names}
    pending=[];updates=0;baseline={n:[] for n in names};train_errors={n:[] for n in names}
    def mature(cutoff):
        nonlocal updates
        while pending and pending[0][0]<cutoff:
            _,idx,x,truth,pred=heapq.heappop(pending)
            for n,y,p in zip(names,truth,pred):
                if np.isfinite(y):
                    train_errors[n].append(float((p-y)**2));models[n].learn_one(x,float(y));baseline[n].append(float(y))
            updates+=1
    for i,context in enumerate(a[0]):
        mature(int(a[5][i]))
        x=token_features(context);truth=[a[2][i],a[3][i],a[4][i]];pred=[models[n].predict_one(x) for n in names]
        heapq.heappush(pending,(int(a[6][i]),i,x,truth,pred))
    mature(int(b[5].min()))
    assert not pending
    means={n:float(np.mean(baseline[n])) for n in names}
    errors={n:[] for n in names};base_errors={n:[] for n in names};detector=drift.ADWIN();alarms=0;predicted=[]
    for i,context in enumerate(b[0]):
        x=token_features(context);pred=[models[n].predict_one(x) for n in names];truth=[b[2][i],b[3][i],b[4][i]]
        predicted.append(pred)
        for n,y,p in zip(names,truth,pred):
            if np.isfinite(y):errors[n].append(float((p-y)**2));base_errors[n].append(float((means[n]-y)**2))
    # Drift diagnostics arrive at target time; they do not alter frozen evaluation weights.
    for i in np.argsort(b[6],kind='stable'):
        loss=(predicted[i][0]-b[2][i])**2
        detector.update(float(loss));alarms+=int(detector.drift_detected)
    result={'status':'river_receipt_tokens_development','river_version':river.__version__,'qualified':False,'orders_enabled':False,'policy':POLICY,'tokenizer_fit_hours':[hours[0]['hour'].iloc[0]],'learning_hours':[h['hour'].iloc[0] for h in hours[1:3]],'training_samples':len(a[0]),'matured_training_updates':updates,'evaluation_samples':len(b[0]),'evaluation_weights_frozen':True,'training_label_rule':'learn only when target receipt < next decision receipt','scores':{n:{'model_mse':float(np.mean(errors[n])),'baseline_mse':float(np.mean(base_errors[n])),'examples':len(errors[n])} for n in names},'return_error_adwin_alarms':alarms,'limits':['Previously examined five-hour development corpus, not untouched validation.','Different tokenizer warmup and two-hour learning protocol: not directly comparable with the five-epoch transformer.','Linear token-frequency/latest-category models, not an LLM or a deep event model.','Raw volatility head is unconstrained; no execution costs, latency allowance or profit test.','Drift detection is descriptive; no automatic reset or strategy promotion.'],'raw_trade_sources':audit,'source_sha256':{p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted((root/'data/frozen').glob('2026-*d09*.csv'))}}
    out=root/'docs/market_tokens/river_trial';out.mkdir(parents=True,exist_ok=True)
    (out/'RESULTS.json').write_text(json.dumps(result,indent=2)+'\n')
    state={'river_version':river.__version__,'optimizer':'SGD','learning_rate':.01,'l2':.0001,'clip_gradient':10,'models':{n:{'weights':dict(m.weights),'intercept':float(m.intercept)} for n,m in models.items()},'tokenizer':{'vocab':tk.vocab,'binners':{f:{k:v.tolist() if isinstance(v,np.ndarray) else v for k,v in vars(bb).items()} for f,bb in tk.b.items()}}}
    (out/'STATE.json').write_text(json.dumps(state,indent=2)+'\n')
    restored={n:linear_model.LinearRegression(optimizer=optim.SGD(.01),l2=.0001,clip_gradient=10) for n in names}
    for n,m in restored.items():
        # River 0.26.1 weights is a copied dictionary; restore its internal VectorDict.
        for key,value in state['models'][n]['weights'].items():m._weights[key]=value
        m.intercept=state['models'][n]['intercept']
    delta=max(abs(restored[n].predict_one(token_features(b[0][0]))-predicted[0][j]) for j,n in enumerate(names));assert delta<1e-10
    (out/'AUDIT.json').write_text(json.dumps({'restored_prediction_max_difference':delta,'matured_updates_match_samples':updates==len(a[0]),'training_targets_before_evaluation':True,'code_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest()},indent=2)+'\n')
    print(json.dumps({k:result[k] for k in ['river_version','training_samples','evaluation_samples','scores','return_error_adwin_alarms']},indent=2))
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--repo',default='.');p.add_argument('--upload',required=True);a=p.parse_args();main(a.repo,a.upload)
