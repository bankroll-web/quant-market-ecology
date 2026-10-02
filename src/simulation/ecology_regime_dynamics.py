"""Observed regime transitions with explicit gap boundaries; diagnostic Markov benchmark."""
import argparse
import csv
import hashlib
import json
import math
from pathlib import Path
import numpy as np
from .ecology_mechanics_replication import load_frozen
from .ecology_price_mechanics import bootstrap_mean,NS
from .robust_ecology_response import HOURS

STATES=('no_signed_flow','low_pressure','high_reinforces','high_opposes','high_neutral')
ALPHA=.5


def state(row,cut):
    if row['signed_btc']==0:return 'no_signed_flow'
    if abs(row['trade_pressure'])<cut:return 'low_pressure'
    direction=row['signed_btc']*row['display_pressure']
    return 'high_reinforces' if direction>0 else 'high_opposes' if direction<0 else 'high_neutral'


def contiguous(a,b):
    return a['episode']==b['episode'] and a['end_ns']==b['start_ns']


def read_windows(path):
    with Path(path).open() as handle:
        rows=[]
        for raw in csv.DictReader(handle):
            rows.append({k:int(raw[k]) for k in ('start_ns','end_ns','episode')}|
                        {k:float(raw[k]) for k in ('signed_btc','trade_pressure','display_pressure','duration_seconds','move_bps')}|
                        {'fresh_250ms':raw['fresh_250ms']=='True'})
    if any(b['start_ns']<a['end_ns'] for a,b in zip(rows,rows[1:])):raise ValueError('Overlapping/unordered windows')
    return rows


def summarize(rows,cut):
    labels=[state(r,cut) for r in rows];index={s:i for i,s in enumerate(STATES)}
    counts=np.zeros((len(STATES),len(STATES)),dtype=int);pairs=[];segments=[];start=0
    for i in range(1,len(rows)):
        if contiguous(rows[i-1],rows[i]):
            counts[index[labels[i-1]],index[labels[i]]]+=1;pairs.append((i-1,i))
        else:segments.append((start,i));start=i
    if rows:segments.append((start,len(rows)))
    runs={s:[] for s in STATES}
    for a,b in segments:
        i=a
        while i<b:
            j=i+1
            while j<b and labels[j]==labels[i]:j+=1
            runs[labels[i]].append(dict(windows=j-i,observed_seconds=sum(r['duration_seconds'] for r in rows[i:j]),
                                       left_censored=i==a,right_censored=j==b))
            i=j
    detail={}
    for s in STATES:
        selected=[r for r,label in zip(rows,labels) if label==s];rr=runs[s]
        complete=[r for r in rr if not r['left_censored'] and not r['right_censored']]
        detail[s]=dict(windows=len(selected),runs=len(rr),completed_runs=len(complete),
                       boundary_censored_runs=sum(r['left_censored'] or r['right_censored'] for r in rr),
                       median_observed_run_seconds=float(np.median([r['observed_seconds'] for r in rr])) if rr else None,
                       mean_completed_run_seconds=float(np.mean([r['observed_seconds'] for r in complete])) if complete else None,
                       unchanged_midpoint_fraction=sum(abs(r['move_bps'])<=1e-12 for r in selected)/len(selected) if selected else None)
    return dict(windows=len(rows),eligible_transitions=len(pairs),excluded_boundaries=max(0,len(rows)-1-len(pairs)),
                contiguous_segments=len(segments),transition_counts=counts.tolist(),regimes=detail),pairs,labels


def fit(counts):
    c=np.array(counts,dtype=float);markov=(c+ALPHA)/(c.sum(1,keepdims=True)+len(STATES)*ALPHA)
    destinations=c.sum(0);iid=(destinations+ALPHA)/(destinations.sum()+len(STATES)*ALPHA)
    return dict(markov=markov.tolist(),iid=iid.tolist(),dirichlet_alpha_per_cell=ALPHA)


def score(rows,pairs,labels,model):
    lookup={s:i for i,s in enumerate(STATES)};a=[];b=[];blocks=[]
    for i,j in pairs:
        source=lookup[labels[i]];target=lookup[labels[j]]
        a.append(-math.log2(model['markov'][source][target]));b.append(-math.log2(model['iid'][target]))
        blocks.append(rows[i]['start_ns']//(60*NS))
    return dict(transitions=len(pairs),markov_log_loss_bits=float(np.mean(a)) if a else None,
                iid_log_loss_bits=float(np.mean(b)) if b else None,
                iid_minus_markov_loss_bits=bootstrap_mean([y-x for x,y in zip(a,b)],blocks,blocks))


def run(baseline,base_windows,replication_windows,out):
    frozen=load_frozen(baseline);cut=frozen['thresholds']['high_trade_pressure'];data={};hashes={}
    for h in HOURS:
        p=Path(replication_windows if h in ('2026-05-26_03','2026-05-26_09') else base_windows)/f'{h}_windows.csv'
        data[h]=read_windows(p);hashes[h]=hashlib.sha256(p.read_bytes()).hexdigest()
    training,_,_=summarize(data[HOURS[0]],cut);model=fit(training['transition_counts']);reports={}
    for h,rows in data.items():
        summary,pairs,labels=summarize(rows,cut)
        fresh=[r for r in rows if r['fresh_250ms']];fs,fp,fl=summarize(fresh,cut)
        reports[h]=dict(summary=summary,scores=score(rows,pairs,labels,model),fresh_summary=fs,fresh_scores=score(fresh,fp,fl,model))
    result=dict(status='observed_regime_dynamics_not_validated_simulator',training_hour=HOURS[0],states=list(STATES),
                pressure_cut=cut,model=model,input_sha256=hashes,results=reports,
                limitations=['Same inspected two-day archive; no untouched final periods.',
                  'States describe relative pressure/liquidity signs, not participant identity or persistent buy/sell direction.',
                  'Exact adjacent endpoints and same episode are required; filtered windows break continuity. No interpolation across missing observations.',
                  'Run lengths are observed segments. Boundary censoring and selected gaps prevent population lifetime estimates.',
                  'Smoothed first-order transition probabilities are a benchmark, not proof of a Markov market or calibrated event intensities.',
                  'Half-count smoothing assigns prior probability to unsupported states; these are not measured occurrences.',
                  'Next-state log loss measures a regime diagnostic, not price prediction, executable profit or live policy qualification.'])
    out=Path(out);out.mkdir(parents=True,exist_ok=True);(out/'report.json').write_text(json.dumps(result,indent=2)+'\n');return result


if __name__=='__main__':
    p=argparse.ArgumentParser()
    for key in ('baseline','base-windows','replication-windows','out'):p.add_argument('--'+key,required=True)
    a=p.parse_args();run(a.baseline,a.base_windows,a.replication_windows,a.out)
