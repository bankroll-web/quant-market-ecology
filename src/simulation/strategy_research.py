"""Frozen exploratory strategy comparison on receipt-time post-update books.

Quote-based paper proxies, not queue/fill simulation or market qualification.
"""
import argparse
from bisect import bisect_left
import csv
import hashlib
import json
import math
from pathlib import Path
import numpy as np

HOURS=('2026-05-25_12','2026-05-25_18','2026-05-26_15','2026-05-26_21')
FEATURES=('completed_flow_over_depth','decision_obi','log_total_flow',
          'completed_window_return_bps','decision_spread_bps','log_depth')
NS=1_000_000_000
LATENCY=100_000_000
HORIZON=5*NS
TOLERANCE=250_000_000
FEE_BPS=2.
SLIPPAGE_BPS=.5
THRESHOLD_BPS=2*(FEE_BPS+SLIPPAGE_BPS)


def load(flow_path, book_path, horizon_ns=HORIZON, latency_ns=LATENCY, retain_unresolved=False):
    if not 0 < latency_ns < horizon_ns:raise ValueError('Latency must be positive and less than horizon')
    with Path(book_path).open(newline='') as f: book=list(csv.DictReader(f))
    times=[int(r['received_time_ns']) for r in book]
    if any(b<a for a,b in zip(times,times[1:])): raise ValueError('Backwards book time')
    # Last message at a duplicate timestamp is available at that timestamp.
    states={(r['received_time_ns'],r['episode']):i for i,r in enumerate(book)}
    with Path(flow_path).open(newline='') as f: flow=list(csv.DictReader(f))
    rows=[]; audit=dict(decisions=0,stale_decisions=0,missing_entry=0,missing_exit=0,embargoed=0)
    next_start=-1
    if retain_unresolved:audit['unresolved']=[]
    for r in sorted(flow,key=lambda r:int(r['end_received_ns'])):
        decision=int(r['end_received_ns']); start=int(r['start_received_ns'])
        if start<next_start: audit['embargoed']+=1;continue
        i=states.get((str(decision),r['episode']))
        if i is None:raise ValueError('Missing exact decision-state join')
        state=book[i];audit['decisions']+=1
        age=(decision-int(state['event_time_ms'])*1_000_000)/1_000_000
        if not 0<=age<=250: audit['stale_decisions']+=1;continue
        depth=float(state['post_bid_depth_10bps'])+float(state['post_ask_depth_10bps'])
        mid=float(state['post_mid'])
        if depth<=0 or mid<=0:raise ValueError('Invalid decision depth/price')
        x=[float(r['signed_btc'])/depth,float(state['post_obi_top']),
           math.log1p(float(r['absolute_trade_btc'])),float(r['mid_log_return_bps']),
           float(state['post_spread'])/mid*10000,math.log1p(depth)]
        if not all(math.isfinite(v) for v in x):raise ValueError('Nonfinite features')
        entry_target=decision+latency_ns;exit_target=decision+horizon_ns
        j=bisect_left(times,entry_target,i+1);k=bisect_left(times,exit_target,i+1)
        def endpoint(index,target):
            return index<len(book) and book[index]['episode']==r['episode'] and times[index]-target<=TOLERANCE
        # An unresolved decision reserves its complete scheduled interval too.
        next_start=exit_target+TOLERANCE
        if not endpoint(j,entry_target):audit['missing_entry']+=1;continue
        if not endpoint(k,exit_target):
            audit['missing_exit']+=1
            if retain_unresolved:audit['unresolved'].append(dict(decision_ns=decision,x=x,flow_sign=int(np.sign(float(r['signed_btc'])))))
            continue
        a,b=book[j],book[k]
        quotes=[float(v[n]) for v in (a,b) for n in ('post_best_bid','post_best_ask')]
        if min(quotes)<=0:raise ValueError('Nonpositive quote')
        y=10000*math.log(float(b['post_mid'])/float(a['post_mid']))
        # Long crosses ask then bid; short sells bid and buys ask.
        long=10000*(quotes[2]/quotes[1]-1)
        short=10000*(quotes[0]-quotes[3])/quotes[0]
        rows.append(dict(decision_ns=decision,entry_ns=times[j],exit_ns=times[k],x=x,y=y,
                         long_quote_bps=long,short_quote_bps=short,flow_sign=int(np.sign(float(r['signed_btc'])))))
    audit['resolved_rows']=len(rows)
    return rows,audit


def fit(rows,kind):
    if len(rows)<10:raise ValueError('Insufficient training observations')
    x=np.array([r['x'] for r in rows]);y=np.array([r['y'] for r in rows])
    center=x.mean(0);scale=x.std(0);scale[scale==0]=1;z=(x-center)/scale
    intercept=float(y.mean());model=dict(kind=kind,center=center.tolist(),scale=scale.tolist(),intercept=intercept,alpha=1.)
    if kind=='ridge':
        model['weights']=np.linalg.solve(z.T@z+np.eye(z.shape[1]),z.T@(y-intercept)).tolist()
    elif kind=='rbf_kernel_ridge':
        # Fixed bandwidth, no test-data tuning; nonlinear supervised learning.
        gamma=1/len(FEATURES);dist=np.maximum(0,(z*z).sum(1)[:,None]+(z*z).sum(1)[None,:]-2*z@z.T)
        model.update(gamma=gamma,train_z=z.tolist(),weights=np.linalg.solve(np.exp(-gamma*dist)+np.eye(len(z)),y-intercept).tolist())
    else:raise ValueError('Unknown model')
    return model


def predict(model,rows):
    if not rows:return np.array([])
    z=(np.array([r['x'] for r in rows])-model['center'])/model['scale']
    if model['kind']=='ridge':return model['intercept']+z@model['weights']
    train=np.array(model['train_z']);dist=np.maximum(0,(z*z).sum(1)[:,None]+(train*train).sum(1)[None,:]-2*z@train.T)
    return model['intercept']+np.exp(-model['gamma']*dist)@model['weights']


def paper(rows,signals,round_trip_cost=THRESHOLD_BPS):
    returns=[(r['long_quote_bps'] if signal>0 else r['short_quote_bps'])-round_trip_cost
             for r,signal in zip(rows,signals) if signal]
    equity=peak=drawdown=0.
    for value in returns:
        equity+=value;peak=max(peak,equity);drawdown=max(drawdown,peak-equity)
    return dict(resolved_opportunities=len(rows),trades=len(returns),
                mean_net_bps=float(np.mean(returns)) if returns else None,
                summed_net_bps=float(sum(returns)),max_cumulative_drawdown_bps=drawdown,
                win_fraction=sum(v>0 for v in returns)/len(returns) if returns else None,
                positive_sum_bps=sum(max(0,v) for v in returns),negative_sum_bps=sum(min(0,v) for v in returns))


def run(flow_dir,book_dir,out):
    datasets={};audits={};hashes={}
    for hour in HOURS:
        fp=Path(flow_dir)/f'{hour}_all_messages.csv';bp=Path(book_dir)/f'BTCUSDT_orderbook_{hour}_observed_changes.csv'
        datasets[hour],audits[hour]=load(fp,bp)
        hashes[hour]={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in (fp,bp)}
    train=datasets[HOURS[0]];models={kind:fit(train,kind) for kind in ('ridge','rbf_kernel_ridge')}
    scores={};prediction_rows=[]
    for hour,rows in datasets.items():
        y=np.array([r['y'] for r in rows]);policies={
            'no_trade':np.zeros(len(rows)), 'flow_sign':np.array([r['flow_sign'] for r in rows])}
        regression={}
        for name,model in models.items():
            pred=predict(model,rows)
            policies[name]=np.where(np.abs(pred)>THRESHOLD_BPS,np.sign(pred),0)
            regression[name]=dict(rmse_bps=float(np.sqrt(np.mean((pred-y)**2))) if rows else None,
                                  zero_rmse_bps=float(np.sqrt(np.mean(y*y))) if rows else None)
            for r,prediction in zip(rows,pred):prediction_rows.append(dict(hour=hour,model=name,decision_ns=r['decision_ns'],entry_ns=r['entry_ns'],exit_ns=r['exit_ns'],predicted_bps=float(prediction),observed_mid_return_bps=r['y'],signal=int(np.sign(prediction)) if abs(prediction)>THRESHOLD_BPS else 0))
        scores[hour]=dict(role='train' if hour==HOURS[0] else 'validation' if hour==HOURS[1] else 'previously_inspected_test',regression=regression,
                         paper={name:{str(cost):paper(rows,signals,cost) for cost in (0.,THRESHOLD_BPS,10.)} for name,signals in policies.items()})
    validation=scores[HOURS[1]]['paper'];winner=max(validation,key=lambda name:validation[name][str(THRESHOLD_BPS)]['summed_net_bps'])
    result=dict(status='research_only_not_qualified',hypothesis='Completed signed flow and current book state predict the subsequent 5-second response sufficiently to overcome execution costs.',features=list(FEATURES),train_hour=HOURS[0],validation_hour=HOURS[1],test_hours=list(HOURS[2:]),
                selected_by_validation=winner,latency_ms=LATENCY/1e6,horizon_seconds=5,endpoint_tolerance_ms=TOLERANCE/1e6,
                fee_bps_per_side=FEE_BPS,extra_slippage_bps_per_side=SLIPPAGE_BPS,signal_threshold_bps=THRESHOLD_BPS,audits=audits,scores=scores,input_sha256=hashes,
                limits=['All four hours were previously examined: no pristine final test.',
                        'Only four discontinuous hours over two days, not adequate regime coverage.',
                        'Missing entries/exits are reported but unresolved inventory losses cannot be reconstructed; scores are conditional on resolved episodes.',
                        'Displayed best quotes are small-order execution proxies; size, queue fills, hidden liquidity and market impact are not established.',
                        'Fees and slippage are explicit assumptions, not verified account terms; no funding, margin or liquidation modeling.',
                        'Historical Binance futures results must not be transferred to the Kraken spot live feed.',
                        'Summed basis points are equal-unit opportunity diagnostics, not a compounded portfolio return.',
                        'No participant identity or measured option gamma in the features.'])
    out=Path(out);out.mkdir(parents=True,exist_ok=True)
    (out/'report.json').write_text(json.dumps(result,indent=2)+'\n')
    (out/'models.json').write_text(json.dumps(models,indent=2)+'\n')
    if prediction_rows:
        with (out/'predictions.csv').open('w',newline='') as f:
            w=csv.DictWriter(f,fieldnames=prediction_rows[0]);w.writeheader();w.writerows(prediction_rows)
    return result

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--flow-dir',type=Path,required=True);p.add_argument('--book-dir',type=Path,required=True);p.add_argument('--out',type=Path,required=True);a=p.parse_args()
    print(json.dumps(run(a.flow_dir,a.book_dir,a.out),indent=2))
