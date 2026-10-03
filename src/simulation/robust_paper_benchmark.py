"""Exploratory bounded-feature Huber/ridge comparison; not a trading promotion."""
import json
from pathlib import Path
import numpy as np
from .observed_ecology_environment import load,examples
from .paper_engine_benchmark import features
from .forecast_evaluation import gate_training

def transform(x):
    x=np.array(x,dtype=float,copy=True);x[:,4]=np.arcsinh(x[:,4]);return x

def fit(x,y):
    x=transform(x);center=np.median(x,axis=0);lo,hi=np.quantile(x,[.25,.75],axis=0);scale=hi-lo;scale=np.where(scale>1e-12,scale,1)
    z=np.column_stack([np.ones(len(x)),np.clip((x-center)/scale,-5,5)])
    delta=max(float(1.345*1.4826*np.median(np.abs(y-np.median(y)))),.01)
    w=np.zeros(z.shape[1]);w[0]=np.median(y);pen=np.eye(z.shape[1]);pen[0,0]=0
    for iteration in range(100):
        residual=y-z@w;weights=np.minimum(1,delta/np.maximum(np.abs(residual),1e-12));new=np.linalg.solve(z.T@(weights[:,None]*z)+.1*len(x)*pen,z.T@(weights*y))
        if np.max(np.abs(new-w))<1e-9:w=new;break
        w=new
    return dict(center=center.tolist(),scale=scale.tolist(),weights=w.tolist(),delta_bps=delta,iterations=iteration+1,clip=5,ridge=.1)

def predict(x,m):
    normalized=(transform(x)-m['center'])/m['scale'];clipped=(np.abs(normalized)>m['clip']).any(1)
    return np.column_stack([np.ones(len(x)),np.clip(normalized,-m['clip'],m['clip'])])@m['weights'],clipped

def run(root):
    root=Path(root);paths=sorted((root/'data/processed/mechanics_study_states').glob('*_observed_changes.csv'))+sorted((root/'data/processed/mechanics_replication_states').glob('*_observed_changes.csv'));first=next(p for p in paths if '2026-05-25_00' in p.name);d=examples(load(first));cut=d[len(d)//2]['decision_ns'];tr=[r for r in d if r['label']['label_available_ns']<=cut];gate_training(cut,[r['label'] for r in tr]);m=fit(np.array([features(r['observation']) for r in tr]),np.array([r['label']['return_bps'] for r in tr]));rows=[]
    old=json.loads((root/'docs/history30/PAPER_ENGINE_BENCHMARK.json').read_text());reference={r['hour']:r for r in old['reports']}
    for path in paths:
        d=[r for r in examples(load(path)) if r['decision_ns']>cut];x=np.array([features(r['observation']) for r in d]);y=np.array([r['label']['return_bps'] for r in d]);p,clipped=predict(x,m)
        rows.append(dict(hour=path.name,examples=len(d),clipped_feature_rows=int(clipped.sum()),robust_mse=float(np.mean((p-y)**2)),ordinary_mse=reference[path.name]['model_mse'],zero_mse=float(np.mean(y*y)),max_absolute_forecast_bps=float(np.max(np.abs(p))),threshold_8_bps_crossings=int(np.sum(np.abs(p)>8))))
    result=dict(status='exploratory_robust_regression_comparison',qualified=False,training_examples=len(tr),cutoff_ns=cut,model=m,reports=rows,limits=['Method chosen after observing ordinary-regression failures on these samples; no independent evaluation.','Feature clipping bounds extrapolation numerically but does not qualify clipped states for trading.','Huber loss reduces sensitivity to large residuals; it cannot manufacture information or an edge.','Historical labels can overlap; samples are not independent. No costs/portfolio evaluation or live model replacement.'])
    (root/'docs/history30/ROBUST_PAPER_BENCHMARK.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(rows,indent=2))
if __name__=='__main__':
    import sys
    run(sys.argv[1])
