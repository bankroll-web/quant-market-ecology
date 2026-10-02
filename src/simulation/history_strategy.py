"""Frozen short-history price-response ablation; quote-based paper research only."""
import argparse
import csv
from collections import deque
import hashlib
import json
import math
from pathlib import Path
import numpy as np
from .strategy_research import HOURS, FEATURES, load, fit, predict
from .regime_research import evaluate

HISTORY_FEATURES = tuple(f'lag{lag}_{name}' for lag in (1,2) for name in ('flow_over_current_depth','log_trade_volume','return_bps','available'))


def history_map(path):
    with Path(path).open() as handle:rows=list(csv.DictReader(handle))
    history=deque(maxlen=2); result={};previous_end=None;episode=None
    for r in rows:
        start,end=int(r['start_received_ns']),int(r['end_received_ns'])
        if end<=start or previous_end is not None and end<=previous_end:
            raise ValueError('Nonpositive or unordered flow window')
        if episode!=r['episode'] or previous_end is None or abs(start-previous_end)>1000:
            history.clear()
        result[end]=list(reversed(history))
        values=[float(r[k]) for k in ('signed_btc','absolute_trade_btc','mid_log_return_bps')]
        if not all(math.isfinite(x) for x in values) or values[1]<0:raise ValueError('Invalid flow feature')
        history.append(values);previous_end=end;episode=r['episode']
    return result


def augment(rows, histories):
    result=[]
    for r in rows:
        depth=math.expm1(r['x'][5])
        if depth<=0:raise ValueError('Invalid current depth')
        x=list(r['x']);past=histories[r['decision_ns']]
        for lag in range(2):
            if lag<len(past):
                signed,volume,ret=past[lag];x.extend([signed/depth,math.log1p(volume),ret,1.])
            else:x.extend([0.,0.,0.,0.])
        result.append({**r,'x':x})
    return result


def actions(model, rows, cost):
    predictions=predict(model,rows)
    # Available current spread, not realized future spread, gates decisions.
    return np.array([int(np.sign(p)) if abs(p)>cost+r['x'][4] else 0 for r,p in zip(rows,predictions)])


def run(flow_dir,book_dir,out):
    data={};unknown={};audits={};hashes={}
    for hour in HOURS:
        flow=Path(flow_dir)/f'{hour}_all_messages.csv'
        book=Path(book_dir)/f'BTCUSDT_orderbook_{hour}_observed_changes.csv'
        rows,audit=load(flow,book,retain_unresolved=True)
        past=history_map(flow)
        data[hour]=dict(snapshot_ridge=rows,history_ridge=augment(rows,past))
        unknown[hour]=dict(snapshot_ridge=audit.pop('unresolved'))
        unknown[hour]['history_ridge']=augment(unknown[hour]['snapshot_ridge'],past)
        audits[hour]=audit
        hashes[hour]={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in (flow,book)}
    models={kind:fit(data[HOURS[0]][kind],'ridge') for kind in ('snapshot_ridge','history_ridge')}
    scores={};regression={}
    for hour in HOURS:
        scores[hour]={};regression[hour]={}
        for name in ('no_trade','snapshot_ridge','history_ridge'):
            key='snapshot_ridge' if name=='no_trade' else name
            rows=data[hour][key];missing=unknown[hour][key]
            scores[hour][name]={}
            for cost in (0.,5.,10.):
                a=np.zeros(len(rows)) if name=='no_trade' else actions(models[name],rows,cost)
                b=np.zeros(len(missing)) if name=='no_trade' else actions(models[name],missing,cost)
                scores[hour][name][str(cost)]=evaluate(rows,missing,a,b,cost)
            if name!='no_trade':
                pred=predict(models[name],rows);y=np.array([r['y'] for r in rows])
                regression[hour][name]=dict(rmse_bps=float(np.sqrt(np.mean((pred-y)**2))) if len(rows) else None,
                                           zero_rmse_bps=float(np.sqrt(np.mean(y*y))) if len(rows) else None)
    eligible=[n for n in models if scores[HOURS[1]][n]['5.0']['trades']>=5 and scores[HOURS[1]][n]['5.0']['stress_50bps_sum']>0]
    winner=max(eligible,key=lambda n:scores[HOURS[1]][n]['5.0']['stress_50bps_sum'],default='no_trade')
    report=dict(status='exploratory_not_qualified',hypothesis='Two earlier completed contiguous flow windows improve five-second cost-adjusted trading over a current-window ridge baseline.',
                selection=winner,features=list(FEATURES)+list(HISTORY_FEATURES),train_hour=HOURS[0],validation_hour=HOURS[1],later_inspected_hours=list(HOURS[2:]),
                horizon_seconds=5,latency_ms=100,endpoint_tolerance_ms=250,round_trip_cost_bps=5,selection_rule='At least five resolved validation trades and positive 50bps missing-exit stress; otherwise no_trade',
                scores=scores,regression=regression,audits=audits,input_sha256=hashes,
                limits=['Previously inspected hours and repeated hypotheses: no untouched test or multiple-testing-adjusted proof of alpha.',
                        'Missing-exit penalties are hypothetical stresses, not measured losses or worst-case bounds.',
                        'Quote-based small-order proxies omit queues, size, impact, funding and liquidations; costs are assumptions.',
                        'History resets at gaps/episodes and ignores supplied forward-return columns. Scaling and ridge weights use training rows only.',
                        'This is a history-state baseline, not a reproduction of LSTM/DQN/PPO or live execution.',
                        'Summed bps are equal-unit diagnostics, not compounded portfolio returns; historical futures are separate from live Coinbase spot.'])
    out=Path(out);out.mkdir(parents=True,exist_ok=True)
    (out/'report.json').write_text(json.dumps(report,indent=2)+'\n')
    (out/'models.json').write_text(json.dumps(models,indent=2)+'\n')
    return report

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--flow-dir',required=True);p.add_argument('--book-dir',required=True);p.add_argument('--out',required=True);a=p.parse_args()
    r=run(a.flow_dir,a.book_dir,a.out);print(json.dumps(dict(selection=r['selection'],regression=r['regression'],scores=r['scores']),indent=2))
