"""Exploratory fixed comparison of contemporaneous ecology response normalizations."""
import argparse
from bisect import bisect_left
import csv
import hashlib
import json
import math
from pathlib import Path
import numpy as np
from .ecology_mechanics_replication import load_frozen
from .ecology_price_mechanics import read_book,bootstrap_mean,NS

HOURS=('2026-05-25_00','2026-05-25_04','2026-05-25_12','2026-05-25_18',
       '2026-05-26_03','2026-05-26_09','2026-05-26_15','2026-05-26_21')
KINDS=('original_linear','training_quantile_clip','asinh_pressure','window_average_depth')


def average_depth(book,start_ns,end_ns,episode,times=None):
    """Left-held received-state queue depth, integrated over the observed window."""
    if times is None:times=[r['received_time_ns'] for r in book]
    i=bisect_left(times,start_ns);j=bisect_left(times,end_ns)
    if i==len(book) or j==len(book) or times[i]!=start_ns or times[j]!=end_ns or j<=i:raise ValueError('Window endpoints missing')
    if any(r['episode']!=episode for r in book[i:j+1]):raise ValueError('Window crosses episode')
    numerator=sum((times[k+1]-times[k])*(book[k]['post_bid_top_qty']+book[k]['post_ask_top_qty'])/2 for k in range(i,j))
    depth=numerator/(end_ns-start_ns)
    if not math.isfinite(depth) or depth<=0:raise ValueError('Invalid integrated depth')
    return depth


def load_windows(path,book):
    out=[];times=[r['received_time_ns'] for r in book]
    with Path(path).open() as handle:
        for raw in csv.DictReader(handle):
            row={k:int(raw[k]) for k in ('start_ns','end_ns','episode')}
            row.update({k:float(raw[k]) for k in ('ofi_pressure','ofi_btc','move_bps')})
            row['fresh_250ms']=raw['fresh_250ms']=='True'
            row['window_average_top_depth_btc']=average_depth(book,row['start_ns'],row['end_ns'],row['episode'],times)
            row['average_depth_pressure']=row['ofi_btc']/row['window_average_top_depth_btc']
            out.append(row)
    return out


def feature(rows,kind,transform):
    x=np.array([r['ofi_pressure'] for r in rows])
    if kind=='training_quantile_clip':return np.clip(x,transform['clip_low'],transform['clip_high'])
    if kind=='asinh_pressure':return np.arcsinh(x/transform['asinh_scale'])
    if kind=='window_average_depth':return np.array([r['average_depth_pressure'] for r in rows])
    if kind=='original_linear':return x
    raise ValueError('Unknown response normalization')


def fit(train,kind,transform,alpha=1.):
    x=feature(train,kind,transform);y=np.array([r['move_bps'] for r in train]);center=float(x.mean());scale=float(x.std()) or 1.
    z=(x-center)/scale;intercept=float(y.mean());weight=float(z@(y-intercept)/(z@z+alpha))
    return dict(center=center,scale=scale,intercept=intercept,weight=weight,alpha=alpha)


def prediction(rows,kind,transform,model):
    return model['intercept']+(feature(rows,kind,transform)-model['center'])/model['scale']*model['weight']


def score(rows,kind,transform,model,baseline_prediction):
    y=np.array([r['move_bps'] for r in rows]);pred=prediction(rows,kind,transform,model);error=(pred-y)**2
    denom=float(((y-y.mean())**2).sum());worst=max(1,math.ceil(.01*len(rows)));total=float(error.sum())
    diff=(baseline_prediction-y)**2-error;blocks=[r['start_ns']//(60*NS) for r in rows]
    return dict(windows=len(rows),rmse_bps=float(np.sqrt(error.mean())),zero_response_rmse_bps=float(np.sqrt(np.mean(y*y))),
                descriptive_r_squared=1-total/denom if denom else None,
                largest_absolute_fit_bps=float(np.max(np.abs(pred))),
                worst_one_percent_squared_error_fraction=float(np.sort(error)[-worst:].sum()/total) if total else None,
                baseline_minus_candidate_mse_bps_squared=bootstrap_mean(diff.tolist(),blocks,blocks))


def run(baseline,spec_path,base_windows,replication_windows,base_states,replication_states,out):
    frozen=load_frozen(baseline);spec=json.loads(Path(spec_path).read_text())
    if spec['training_hour']!=HOURS[0] or tuple(spec['models'])!=KINDS or spec['clip_quantiles']!=[.01,.99] or spec['ridge_alpha']!=1 or spec['fit_or_select_on_comparison_periods']:
        raise ValueError('Comparison specification changed')
    data={};hashes={}
    for h in HOURS:
        extra=h in ('2026-05-26_03','2026-05-26_09')
        wp=Path(replication_windows if extra else base_windows)/f'{h}_windows.csv'
        bp=Path(replication_states if extra else base_states)/f'BTCUSDT_orderbook_{h}_observed_changes.csv'
        book=read_book(bp);expected=json.loads(bp.with_suffix('.json').read_text())['calibration_intervals']
        if len(book)!=expected:raise ValueError('Incomplete source reconstruction')
        data[h]=load_windows(wp,book);hashes[h]={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in (wp,bp)}
    train=data[HOURS[0]];x=np.array([r['ofi_pressure'] for r in train])
    transform=dict(clip_low=float(np.quantile(x,.01)),clip_high=float(np.quantile(x,.99)),asinh_scale=float(x.std()) or 1.)
    models={k:fit(train,k,transform) for k in KINDS};original=frozen['models']['book_only']
    for key,expected in [('center',original['center'][0]),('scale',original['scale'][0]),('weight',original['weights'][0]),('intercept',original['intercept'])]:
        if not math.isclose(models['original_linear'][key],expected,rel_tol=1e-12,abs_tol=1e-12):raise ValueError('Original baseline fit did not reproduce')
    reports={}
    for h,rows in data.items():
        base=prediction(rows,'original_linear',transform,models['original_linear']);fresh=[r for r in rows if r['fresh_250ms']]
        fresh_base=prediction(fresh,'original_linear',transform,models['original_linear'])
        reports[h]=dict(all={k:score(rows,k,transform,m,base) for k,m in models.items()},
                        fresh={k:score(fresh,k,transform,m,fresh_base) for k,m in models.items()})
    result=dict(status='exploratory_contemporaneous_response_comparison_no_promotion',specification=spec,
                specification_sha256=hashlib.sha256(Path(spec_path).read_bytes()).hexdigest(),training_hour=HOURS[0],
                thresholds=transform,models=models,input_sha256=hashes,results=reports,
                limitations=['All periods were inspected before this experiment; hypotheses were specified after the known extrapolation failure. This is not untouched validation.',
                 'Targets and features occur during the same window; OFI and average depth include within-window information. Scores are explanatory, not forecast accuracy.',
                 'Quantile clipping limits the feature; asinh only compresses it and is unbounded. No method guarantees stable price dynamics or net profit.',
                 'Average depth is left-held receipt-time displayed depth, not matching-engine event-time depth, hidden liquidity or identified participant inventory.',
                 'Eight discontinuous recordings from two days; bootstrap assumptions and multiple comparisons limit inference.',
                 'No policy selection, trading, execution-cost validation, future-data fitting or live deployment of these calibrations occurred.'])
    out=Path(out);out.mkdir(parents=True,exist_ok=True);(out/'report.json').write_text(json.dumps(result,indent=2)+'\n');return result


if __name__=='__main__':
    p=argparse.ArgumentParser()
    for key in ('baseline','spec','base-windows','replication-windows','base-states','replication-states','out'):p.add_argument('--'+key,required=True)
    a=p.parse_args();run(a.baseline,a.spec,a.base_windows,a.replication_windows,a.base_states,a.replication_states,a.out)
