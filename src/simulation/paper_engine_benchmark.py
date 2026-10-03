"""Historical development check of the live paper engine's expected-return model."""
import json,math,hashlib
from pathlib import Path
import numpy as np
from .observed_ecology_environment import load,examples
from .forecast_evaluation import gate_training
from .paper_signal import fit_return

def features(o):
    depth=o['post_bid_depth_10bps']+o['post_ask_depth_10bps']
    return [o['post_obi_top'],(o['post_bid_depth_10bps']-o['post_ask_depth_10bps'])/depth,math.log(depth),10000*o['post_spread']/o['post_mid'],o['best_quote_ofi_btc']/depth]

def run(root):
    root=Path(root);paths=sorted((root/'data/processed/mechanics_study_states').glob('*_observed_changes.csv'))+sorted((root/'data/processed/mechanics_replication_states').glob('*_observed_changes.csv'))
    first=next(p for p in paths if '2026-05-25_00' in p.name);data=examples(load(first));cut=data[len(data)//2]['decision_ns'];training=[r for r in data if r['label']['label_available_ns']<=cut];gate_training(cut,[r['label'] for r in training]);x=np.array([features(r['observation']) for r in training]);y=np.array([r['label']['return_bps'] for r in training]);reports=[]
    for p in paths:
        rows=load(p);bytime={r['received_time_ns']:r for r in rows};evaluation=[r for r in examples(rows) if r['decision_ns']>cut]
        xe=np.array([features(r['observation']) for r in evaluation]);ye=np.array([r['label']['return_bps'] for r in evaluation]);m=fit_return(x,y,xe,ye);pred=np.column_stack([np.ones(len(xe)),(xe-m['center'])/m['scale']])@m['weights'];supported=((xe>=m['feature_lower'])&(xe<=m['feature_upper'])).all(1);pos=np.where(pred>8,1,np.where(pred<-8,-1,0));pos[~supported]=0;net=[]
        for r,side in zip(evaluation,pos):
            if not side:continue
            start=r['observation'];end=bytime[r['label']['target_end_ns']]
            gross=10000*(end['post_best_bid']/start['post_best_ask']-1) if side==1 else 10000*(start['post_best_bid']-end['post_best_ask'])/start['post_best_bid']
            net.append(gross-6)
        reports.append(dict(hour=p.name,examples=len(evaluation),supported_examples=int(supported.sum()),model_mse=m['mse'],zero_mse=m['zero_mse'],max_absolute_estimate_bps=float(np.max(np.abs(pred))),threshold_candidates=len(net),quote_proxy_mean_net_bps=float(np.mean(net)) if net else None,input_sha256=hashlib.sha256(p.read_bytes()).hexdigest()))
    result=dict(status='historical_paper_engine_development_check',qualified=False,training_examples=len(training),cutoff_ns=cut,entry_threshold_bps=8,reports=reports,limits=['All historical samples previously inspected; no independent validation.','This frozen first-half-hour model differs from current venue-specific live fits.','Historical Binance futures model is not loaded into Kraken or Coinbase.','Immediate top-quote proxies omit execution latency, order size and funding; 6 bps fees/slippage assumed.','Historical labels can overlap by up to 250 ms; counts are not independent observations.','Offline check does not apply every live freshness or age eligibility gate. No candidate promotion.'])
    (root/'docs/history30/PAPER_ENGINE_BENCHMARK.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2))
if __name__=='__main__':
    import sys
    run(sys.argv[1])
