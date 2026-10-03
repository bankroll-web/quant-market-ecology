"""Paper-inspired shallow tree for executable quote returns; offline development only."""
import hashlib
import json
from pathlib import Path
import numpy as np
from sklearn.tree import DecisionTreeRegressor, export_text
from .observed_ecology_environment import load, examples
from .paper_engine_benchmark import features
from .forecast_evaluation import gate_training

FEATURE_NAMES = ['top_book_imbalance', 'depth_imbalance', 'log_depth', 'spread_bps', 'ofi_over_depth', 'bid_display_change_over_depth', 'ask_display_change_over_depth']

def inputs(o):
    depth=o['post_bid_depth_10bps']+o['post_ask_depth_10bps']
    if depth<=0: raise ValueError('Nonpositive depth')
    return features(o)+[(o['bid_add_qty']-o['bid_remove_qty'])/depth,(o['ask_add_qty']-o['ask_remove_qty'])/depth]

def quote_targets(record,end,cost_bps=6):
    start=record['observation']
    return [10000*(end['post_best_bid']/start['post_best_ask']-1)-cost_bps,
            10000*(start['post_best_bid']-end['post_best_ask'])/start['post_best_bid']-cost_bps]

def fit(x,y):
    x=np.asarray(x);y=np.asarray(y)
    if len(x)<80 or not np.isfinite(x).all() or not np.isfinite(y).all(): raise ValueError('Invalid training set')
    model=DecisionTreeRegressor(max_depth=4,min_samples_leaf=40,random_state=91).fit(x,y)
    return model,x.min(axis=0),x.max(axis=0)

def actions(x,fitted,buffer_bps=2):
    model,lo,hi=fitted;x=np.asarray(x);p=model.predict(x)
    supported=((x>=lo)&(x<=hi)&np.isfinite(x)).all(axis=1)
    side=np.where(p[:,0]>=p[:,1],1,-1)
    side[(np.max(p,axis=1)<=buffer_bps)|~supported]=0
    return side,p,supported

def run(root,horizon_seconds=1):
    if horizon_seconds not in (1,5,30): raise ValueError('Supported horizons: 1, 5, 30 seconds')
    root=Path(root)
    paths=sorted((root/'data/processed/mechanics_study_states').glob('*_observed_changes.csv'))+sorted((root/'data/processed/mechanics_replication_states').glob('*_observed_changes.csv'))
    first=next(p for p in paths if '2026-05-25_00' in p.name)
    raw=load(first);bytime={r['received_time_ns']:r for r in raw};records=examples(raw,horizon_ns=int(horizon_seconds*10**9))
    anchor=examples(raw)
    if not anchor: raise ValueError('No valid one-second cutoff anchor')
    cut=anchor[len(anchor)//2]['decision_ns']
    train=[r for r in records if r['label']['label_available_ns']<=cut]
    gate_training(cut,[r['label'] for r in train])
    x=np.array([inputs(r['observation']) for r in train]);y=np.array([quote_targets(r,bytime[r['label']['target_end_ns']]) for r in train])
    if len(train)<80:
        result=dict(status='insufficient_training_examples',qualified=False,horizon_seconds=horizon_seconds,training_examples=len(train),required_training_examples=80,cutoff_ns=cut,reason='Strict continuity filter leaves too few resolved labels for the fixed minimum leaf size. No relaxed timing gate or threshold tuning.')
        out=root/'docs/strategy_papers';out.mkdir(parents=True,exist_ok=True)
        (out/f'ECOLOGY_TREE_{horizon_seconds}S_RESULTS.json').write_text(json.dumps(result,indent=2)+'\n')
        print(json.dumps(result,indent=2));return result
    fitted=fit(x,y);reports=[];net_all=[]
    for path in paths:
        raw=load(path);bytime={r['received_time_ns']:r for r in raw}
        ev=[r for r in examples(raw,horizon_ns=int(horizon_seconds*10**9)) if r['decision_ns']>cut]
        xe=np.array([inputs(r['observation']) for r in ev]);ye=np.array([quote_targets(r,bytime[r['label']['target_end_ns']]) for r in ev])
        side,p,supported=actions(xe,fitted);net=ye[side!=0,(side[side!=0]<0).astype(int)];net_all.extend(net.tolist())
        reports.append(dict(hour=path.name,examples=len(ev),supported_examples=int(supported.sum()),buy=int((side==1).sum()),sell=int((side==-1).sum()),mean_net_bps=float(net.mean()) if len(net) else None,positive_fraction=float((net>0).mean()) if len(net) else None,net_target_mse=float(np.mean((p-ye)**2)),training_constant_mse=float(np.mean((y.mean(axis=0)-ye)**2)),sha256=hashlib.sha256(path.read_bytes()).hexdigest()))
    result=dict(status='paper_inspired_ecology_tree_development',qualified=False,orders_enabled=False,horizon_seconds=horizon_seconds,training_examples=len(train),cutoff_ns=cut,model=dict(max_depth=4,min_samples_leaf=40,seed=91,feature_names=FEATURE_NAMES,feature_lower=fitted[1].tolist(),feature_upper=fitted[2].tolist(),rules=export_text(fitted[0],feature_names=FEATURE_NAMES,decimals=6),training_leaf_net_bps={str(k):y[fitted[0].apply(x)==k].mean(axis=0).tolist() for k in np.unique(fitted[0].apply(x))}),cost_bps=6,net_buffer_bps=2,reports=reports,total_entries=len(net_all),mean_net_bps=float(np.mean(net_all)) if net_all else None,limits=['All eight recordings previously inspected. Adaptation selected after earlier failures; no independent validation.', 'Regression predicts long/short quote net returns, replacing the source equity Gini classifier and technical indicators.', 'No depth or threshold tuning on evaluation results. Training labels must resolve before cutoff.', 'Seven features describe public displayed liquidity, not participant identity; displayed reductions do not identify cancellations.', 'Range guard checks individual features, not full joint distribution. Targets can overlap by up to 250ms.', 'Immediate best-quote proxies omit execution latency, size, funding and borrow constraints. SELL assumes hypothetical short access.', 'Offline timing gates differ from all live feed gates. No live deployment or promotion.'])
    out=root/'docs/strategy_papers';out.mkdir(parents=True,exist_ok=True)
    (out/f'ECOLOGY_TREE_{horizon_seconds}S_RESULTS.json').write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps({k:result[k] for k in ['training_examples','total_entries','mean_net_bps','reports']},indent=2))
    return result

if __name__=='__main__':
    import sys
    run(sys.argv[1],int(sys.argv[2]) if len(sys.argv)>2 else 1)
