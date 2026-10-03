"""Fixed ridge-logistic development comparison, using only received book features."""
import json,hashlib
from pathlib import Path
import numpy as np
from .observed_ecology_environment import load,examples
from .forecast_evaluation import gate_training,score

NAMES=('top_imbalance','depth_imbalance','log_depth','spread_bps','last_bundle_ofi_per_depth')


def features(data):
    out=[]
    for r in data:
        o=r['observation'];bid=o['post_bid_depth_10bps'];ask=o['post_ask_depth_10bps'];depth=bid+ask
        if depth<=0 or o['post_mid']<=0:raise ValueError('Invalid feature denominator')
        out.append([o['post_obi_top'],(bid-ask)/depth,np.log(depth),10000*o['post_spread']/o['post_mid'],o['best_quote_ofi_btc']/depth])
    a=np.array(out,dtype=float)
    if not np.isfinite(a).all():raise ValueError('Nonfinite features')
    return a


def probability(x,w):return 1/(1+np.exp(-np.clip(x@w,-40,40)))


def fit(x,y,ridge=.1):
    if len(x)!=len(y) or not len(y) or ridge<=0:raise ValueError('Invalid training data')
    center=x.mean(axis=0);scale=x.std(axis=0);scale[scale<1e-12]=1.
    z=np.column_stack([np.ones(len(x)),(x-center)/scale]);w=np.zeros(z.shape[1]);penalty=np.ones(len(w))*ridge;penalty[0]=0
    for iteration in range(100):
        p=probability(z,w);gradient=z.T@(p-y)/len(y)+penalty*w
        hessian=(z.T*(p*(1-p)))@z/len(y)+np.diag(penalty)+np.eye(len(w))*1e-10
        step=np.linalg.solve(hessian,gradient);w-=step
        if np.max(np.abs(step))<1e-9:break
    else:raise ValueError('Logistic solver did not converge')
    return dict(center=center.tolist(),scale=scale.tolist(),weights=w.tolist(),ridge=ridge,iterations=iteration+1)


def predict(x,model):
    z=np.column_stack([np.ones(len(x)),(x-np.array(model['center']))/np.array(model['scale'])])
    return probability(z,np.array(model['weights']))


def benchmark(paths,baseline_path,out):
    base=json.loads(Path(baseline_path).read_text());cut=base['training_cutoff_ns']
    if not paths or '2026-05-25_00' not in Path(paths[0]).name:raise ValueError('Training path must be first')
    for path in paths:
        if hashlib.sha256(Path(path).read_bytes()).hexdigest()!=base['input_sha256'].get(Path(path).name):raise ValueError('Frozen source mismatch')
    data=[examples(load(p)) for p in paths]
    train=[r for r in data[0] if r['label']['label_available_ns']<=cut]
    gate_training(cut,[r['label'] for r in train]);y=np.array([int(r['label']['return_bps']>0) for r in train])
    model=fit(features(train),y);reports={}
    for path,rows in zip(paths,data):
        rows=[r for r in rows if r['decision_ns']>cut];p=predict(features(rows),model).tolist();returns=[r['label']['return_bps'] for r in rows]
        measured=score(p,returns,[base['interval_80_bps']]*len(rows));prior=base['reports'][Path(path).stem]['frozen_base_rate']
        reports[Path(path).stem]=dict(model=measured,baseline=prior,brier_difference=measured['brier']-prior['brier'],mean_probability=float(np.mean(p)),actual_positive_fraction=float(np.mean(np.array(returns)>0)))
    result=dict(status='exploratory_logistic_comparison_not_trading_strategy',features=list(NAMES),input_sha256=base['input_sha256'],baseline_sha256=hashlib.sha256(Path(baseline_path).read_bytes()).hexdigest(),training_examples=len(train),training_cutoff_ns=cut,model=model,reports=reports,
        limitations=['Fixed ridge 0.1 and five features chosen for development; no tuning on later scores.',
        'Transforms and coefficients fit only resolved first-half training labels. These previously inspected recordings are not untouched validation.',
        'Binary target treats zero return as nonpositive; class imbalance can dominate Brier improvement.',
        'Intervals are unchanged frozen baseline intervals; the logistic model does not improve volatility or interval calibration.',
        'No confidence intervals, execution model, transaction costs or profitability qualification.'])
    Path(out).write_text(json.dumps(result,indent=2)+'\n');return result
