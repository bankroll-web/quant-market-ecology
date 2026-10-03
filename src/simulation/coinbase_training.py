"""Offline Coinbase fitting from verified completed captures; no order execution."""
import argparse,bisect,json,math
from pathlib import Path
import numpy as np
from .capture_archive import verify_segment
from .ecology_probability_model import fit,predict
from .forecast_evaluation import gate_inputs,gate_training,score


def dataset(manifests):
    records=[]
    for path in manifests:
        meta=json.loads(Path(path).read_text())
        for row in verify_segment(path):
            if row['kind'] in ('coinbase_model_observation','kraken_model_observation'):records.append(dict(row['payload'],session=meta['session']))
    return dataset_records(records)


def dataset_records(records):
    records=list(records)
    records.sort(key=lambda r:r['available_ns'])
    if any(b['available_ns']<=a['available_ns'] for a,b in zip(records,records[1:])):raise ValueError('Duplicate or unordered feature receipts')
    times=[r['available_ns'] for r in records];out=[];next_time=-1;bad=[0]
    for i in range(1,len(records)):
        a,b=records[i-1:i+1]
        bad.append(bad[-1]+int(a['session']!=b['session'] or b['source_update_id']<=a['source_update_id'] or times[i]-times[i-1]>250_000_000))
    for i,r in enumerate(records):
        if times[i]<next_time:continue
        next_time=times[i]+10**9;j=bisect.bisect_left(times,next_time,i+1)
        if j>=len(records) or times[j]-next_time>250_000_000 or bad[j]!=bad[i]:continue
        if any((v['provider'],v['symbol']) not in (('Coinbase Exchange','BTC-USD'),('Kraken','BTC/USD')) or (v['provider'],v['symbol'])!=(r['provider'],r['symbol']) or not 0<=v['available_ns']-v['event_ns']<=250_000_000 for v in records[i:j+1]):continue
        gate_inputs(times[i],[dict(event_ns=r['event_ns'],available_ns=times[i])])
        if len(r['features'])!=5 or not all(math.isfinite(v) for v in r['features']):raise ValueError('Invalid features')
        out.append(dict(provider=r['provider'],symbol=r['symbol'],decision_ns=times[i],features=r['features'],target_end_ns=times[j],label_available_ns=times[j],return_bps=10000*math.log(records[j]['midpoint']/r['midpoint'])))
    return out


def train(manifests,out):
    result=train_examples(dataset(manifests))
    Path(out).write_text(json.dumps(result,indent=2)+'\n');return result


def train_examples(data):
    if len({(r.get('provider','Coinbase Exchange'),r.get('symbol','BTC-USD')) for r in data})>1:
        return dict(status='mixed_venues_rejected',qualified=False)
    if len(data)<400:
        result=dict(status='insufficient_data',usable_examples=len(data),required_minimum=400,qualified=False,
                    note='400 is an engineering floor, not sufficient evidence of robustness or profitability.')
    else:
        cut=data[len(data)//2]['decision_ns'];training=[r for r in data if r['label_available_ns']<=cut];evaluation=[r for r in data if r['decision_ns']>cut]
        gate_training(cut,training);x=np.array([r['features'] for r in training]);y=np.array([int(r['return_bps']>0) for r in training])
        if min(int(y.sum()),int(len(y)-y.sum()))<10:
            return dict(status='insufficient_class_support',qualified=False,usable_examples=len(data))
        model=fit(x,y);p=predict(np.array([r['features'] for r in evaluation]),model).tolist()
        targets=[r['return_bps'] for r in evaluation];interval=list(map(float,np.quantile([r['return_bps'] for r in training],[.1,.9])))
        result=dict(status='offline_development_fit',venue=data[0].get('provider','Coinbase Exchange'),symbol=data[0].get('symbol','BTC-USD'),qualified=False,model=model,
            training_examples=len(training),evaluation_examples=len(evaluation),cutoff_ns=cut,
            scores=score(p,targets,[interval]*len(targets)),baseline=score([float(y.mean())]*len(targets),targets,[interval]*len(targets)),
            limitations=['Receipt-batched feed lacks independent sequence verification.','Chronological second-half comparison only; no untouched-day validation.','No fill, fee, latency, inventory or profit evaluation. Artifact is not loaded automatically into live trading.'])
    return result

if __name__=='__main__':
    ap=argparse.ArgumentParser();ap.add_argument('manifests',nargs='+');ap.add_argument('--out',required=True);a=ap.parse_args();train(a.manifests,a.out)
