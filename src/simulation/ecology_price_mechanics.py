"""Observed trade/book ecology and price response: descriptive, not causal or tradable."""
import argparse
from bisect import bisect_left, bisect_right
from collections import Counter
import csv
import hashlib
import json
import math
from pathlib import Path
import numpy as np
from .book_changes import plain
import pyarrow.parquet as pq

HOURS=('2026-05-25_00','2026-05-25_04','2026-05-25_12','2026-05-25_18','2026-05-26_15','2026-05-26_21')
NS=1_000_000_000
BOOTSTRAPS=1000
FEATURES=('trade_btc_over_start_depth','best_quote_ofi_over_start_top_depth',
          'net_displayed_pressure_over_start_depth','start_obi','log_start_depth','trade_pressure_times_thin')


def read_book(path):
    with Path(path).open() as handle:raw=list(csv.DictReader(handle))
    if any(None in r or any(v is None for v in r.values()) for r in raw):raise ValueError('Incomplete book CSV')
    rows=[]
    for r in raw:
        row={k:(int(v) if k in ('received_time_ns','event_time_ms','episode') else float(v)) for k,v in r.items()}
        if not all(math.isfinite(v) for v in row.values()):raise ValueError('Nonfinite book value')
        rows.append(row)
    if any(b['received_time_ns']<a['received_time_ns'] for a,b in zip(rows,rows[1:])):raise ValueError('Unordered book')
    return rows


def read_trade_observations(path):
    source,temporary=plain(path);trades=[];missing=[];gaps=[];previous=None
    try:
        d=pq.read_table(source,columns=['received_time','trade_time','quantity','price','is_buyer_maker','order_type','trade_id']).to_pydict()
        for t,event,q,p,maker,kind,trade_id in zip(*(d[k] for k in ('received_time','trade_time','quantity','price','is_buyer_maker','order_type','trade_id'))):
            if previous is not None and int(trade_id)>previous[1]+1:gaps.append((previous[0],int(t)))
            previous=(int(t),int(trade_id))
            q=float(q);p=float(p)
            if q==0 and p==0 and kind=='NA':missing.append(int(t));continue
            if q<=0 or p<=0 or not math.isfinite(q+p) or maker is None:raise ValueError('Invalid trade payload')
            trades.append((int(t),q*(-1 if maker else 1),(int(t)-int(event)*1_000_000)/1e6))
    finally:
        if temporary:Path(source).unlink()
    return sorted(trades),sorted(missing),gaps


def build_windows(book,trades,missing_trade_times=(),missing_trade_ranges=()):
    times=[r['received_time_ns'] for r in book];trade_times=[r[0] for r in trades]
    out=[];audit=Counter();next_start=0
    for i,start in enumerate(book):
        if i<next_start:continue
        t0=times[i];end=bisect_left(times,t0+NS,i+1)
        if end>=len(book) or book[end]['episode']!=start['episode']:
            audit['no_same_episode_end']+=1;continue
        t1=times[end];next_start=end
        if t1-t0>1_250_000_000:
            audit['end_sampling_lag']+=1;continue
        window=book[i:end+1]
        if any(r['post_best_bid']>=r['post_best_ask'] or r['post_mid']<=0 for r in window):
            audit['crossed_or_invalid_state']+=1;continue
        # Do not treat a long missing receipt interval as fully observed ecology.
        if any(times[j]-times[j-1]>250_000_000 or
               abs(round(book[j]['exposure_seconds']*NS)-(times[j]-times[j-1]))>1000 for j in range(i+1,end+1)):
            audit['interior_gap']+=1;continue
        a,b=bisect_right(trade_times,t0),bisect_right(trade_times,t1)
        if any(left<t1 and right>t0 for left,right in missing_trade_ranges):
            audit['trade_id_gap_windows']+=1;continue
        if bisect_right(missing_trade_times,t1)>bisect_right(missing_trade_times,t0):
            audit['missing_trade_payload']+=1;continue
        observed=trades[a:b];buy=sum(q for _,q,_ in observed if q>0);sell=-sum(q for _,q,_ in observed if q<0)
        depth=start['post_bid_depth_10bps']+start['post_ask_depth_10bps']
        top=(start['post_bid_top_qty']+start['post_ask_top_qty'])/2
        if depth<=0 or top<=0:raise ValueError('Nonpositive initial depth')
        changes={k:sum(r[k] for r in book[i+1:end+1]) for k in ('bid_add_qty','bid_remove_qty','ask_add_qty','ask_remove_qty','best_quote_ofi_btc')}
        bid_net=changes['bid_add_qty']-changes['bid_remove_qty'];ask_net=changes['ask_add_qty']-changes['ask_remove_qty']
        book_ages=[(r['received_time_ns']-r['event_time_ms']*1_000_000)/1e6 for r in window]
        trade_ages=[age for _,_,age in observed]
        row=dict(start_ns=t0,end_ns=t1,episode=start['episode'],duration_seconds=(t1-t0)/NS,
                 buy_btc=buy,sell_btc=sell,signed_btc=buy-sell,absolute_btc=buy+sell,trade_count=len(observed),
                 start_depth_btc=depth,start_top_depth_btc=top,start_obi=start['post_obi_top'],
                 ofi_btc=changes['best_quote_ofi_btc'],bid_net_btc=bid_net,ask_net_btc=ask_net,
                 trade_pressure=(buy-sell)/depth,ofi_pressure=changes['best_quote_ofi_btc']/top,
                 display_pressure=(bid_net-ask_net)/depth,
                 move_bps=10000*math.log(book[end]['post_mid']/start['post_mid']),
                 fresh_250ms=all(0<=age<=250 for age in book_ages+trade_ages),
                 max_book_age_ms=max(book_ages),max_trade_age_ms=max(trade_ages) if trade_ages else None,
                 bid_added_btc=changes['bid_add_qty'],bid_reduced_btc=changes['bid_remove_qty'],
                 ask_added_btc=changes['ask_add_qty'],ask_reduced_btc=changes['ask_remove_qty'])
        for horizon in (1,5):
            target=t1+horizon*NS;k=bisect_left(times,target,end+1)
            row[f'forward_{horizon}s_bps']=10000*math.log(book[k]['post_mid']/book[end]['post_mid']) if k<len(book) and book[k]['episode']==start['episode'] and times[k]-target<=250_000_000 and all(times[j]-times[j-1]<=250_000_000 and book[j]['post_best_bid']<book[j]['post_best_ask'] for j in range(end+1,k+1)) else None
        out.append(row)
    audit.update(windows=len(out),fresh_windows=sum(r['fresh_250ms'] for r in out),
                 recorded_window_seconds=sum(r['duration_seconds'] for r in out))
    return out,dict(audit)


def thresholds(train):
    pressures=[abs(r['trade_pressure']) for r in train if r['signed_btc']]
    return dict(high_trade_pressure=float(np.quantile(pressures,.75)),
                thin_depth_btc=float(np.median([r['start_depth_btc'] for r in train])))


def categories(row,cuts):
    sign=np.sign(row['signed_btc'])
    if not sign:return ['all','no_signed_trade_flow']
    high=abs(row['trade_pressure'])>=cuts['high_trade_pressure']
    tags=['all','signed_trade_flow','buy_pressure' if sign>0 else 'sell_pressure']
    if high:
        alignment=sign*row['ofi_btc']
        mode='book_agrees' if alignment>0 else 'book_opposes' if alignment<0 else 'book_neutral'
        supply=sign*row['display_pressure']
        supply_mode='display_reinforces' if supply>0 else 'display_opposes' if supply<0 else 'display_neutral'
        tags+=['high_trade_pressure',mode,supply_mode,
               'high_pressure_thin' if row['start_depth_btc']<cuts['thin_depth_btc'] else 'high_pressure_deep']
    return tags


def bootstrap_mean(values,blocks,universe,seed=739):
    if not values:return dict(mean=None,lower=None,upper=None,blocks=0)
    universe=sorted(set(universe));lookup={v:i for i,v in enumerate(universe)}
    sums=np.zeros(len(universe));counts=np.zeros(len(universe))
    for value,block in zip(values,blocks):sums[lookup[block]]+=value;counts[lookup[block]]+=1
    active=int(np.count_nonzero(counts))
    result=dict(mean=float(np.mean(values)),lower=None,upper=None,blocks=active)
    if active<10:return result
    rng=np.random.default_rng(seed);indices=rng.integers(0,len(universe),size=(BOOTSTRAPS,len(universe)))
    denominators=counts[indices].sum(1);valid=denominators>0
    means=sums[indices].sum(1)[valid]/denominators[valid]
    result.update(lower=float(np.quantile(means,.025)),upper=float(np.quantile(means,.975)))
    return result


def describe(rows,universe):
    sign=lambda r:float(np.sign(r['signed_btc']))
    directional=[r for r in rows if sign(r)]
    y=[r['move_bps']*sign(r) for r in directional]
    blocks=[r['start_ns']//(60*NS) for r in directional]
    response=bootstrap_mean(y,blocks,universe)
    result=dict(windows=len(rows),directional_windows=len(y),aligned_mean_bps=response,
                aligned_quantiles_bps={str(q):float(np.quantile(y,q)) for q in (.05,.25,.5,.75,.95)} if y else {},
                aligned_probability=bootstrap_mean([float(v>1e-12) for v in y],blocks,universe),
                opposite_probability=bootstrap_mean([float(v< -1e-12) for v in y],blocks,universe),
                unchanged_probability=bootstrap_mean([float(abs(v)<=1e-12) for v in y],blocks,universe),
                signed_trade_btc=float(sum(r['signed_btc'] for r in rows)),
                mean_start_depth_btc=float(np.mean([r['start_depth_btc'] for r in rows])) if rows else None)
    for horizon in (1,5):
        eligible=[r for r in directional if r[f'forward_{horizon}s_bps'] is not None]
        vals=[r[f'forward_{horizon}s_bps']*sign(r) for r in eligible]
        result[f'forward_{horizon}s']=dict(available=len(eligible),missing=len(directional)-len(eligible),
                                         aligned_mean_bps=bootstrap_mean(vals,[r['start_ns']//(60*NS) for r in eligible],universe))
    return result


def contrast(groups,universe,left,right,block_seconds=60):
    """Conditional mean difference using shared minute-block resamples."""
    universe=sorted(set(universe));lookup={v:i for i,v in enumerate(universe)}
    accum=[];active=[]
    for name in (left,right):
        sums=np.zeros(len(universe));counts=np.zeros(len(universe))
        for r in groups.get(name,[]):
            if not r['signed_btc']:continue
            i=lookup[r['start_ns']//(block_seconds*NS)]
            sums[i]+=float(np.sign(r['signed_btc']))*r['move_bps'];counts[i]+=1
        accum.append((sums,counts));active.append(int(np.count_nonzero(counts)))
    if any(c.sum()==0 for _,c in accum):return dict(mean=None,lower=None,upper=None,active_blocks=active)
    result=dict(mean=float(accum[0][0].sum()/accum[0][1].sum()-accum[1][0].sum()/accum[1][1].sum()),lower=None,upper=None,active_blocks=active)
    if min(active)<10:return result
    indices=np.random.default_rng(937).integers(0,len(universe),(BOOTSTRAPS,len(universe)))
    s0,c0=accum[0];s1,c1=accum[1];n0=c0[indices].sum(1);n1=c1[indices].sum(1);valid=(n0>0)&(n1>0)
    draws=s0[indices].sum(1)[valid]/n0[valid]-s1[indices].sum(1)[valid]/n1[valid]
    result.update(lower=float(np.quantile(draws,.025)),upper=float(np.quantile(draws,.975)))
    return result


def xmatrix(rows,cuts,kind):
    if kind=='trade_only':return np.array([[r['trade_pressure']] for r in rows])
    if kind=='book_only':return np.array([[r['ofi_pressure']] for r in rows])
    return np.array([[r['trade_pressure'],r['ofi_pressure'],r['display_pressure'],r['start_obi'],
                      math.log1p(r['start_depth_btc']),r['trade_pressure']*(r['start_depth_btc']<cuts['thin_depth_btc'])] for r in rows])


def fit(train,cuts,kind):
    x=xmatrix(train,cuts,kind);y=np.array([r['move_bps'] for r in train])
    center=x.mean(0);scale=x.std(0);scale[scale==0]=1;z=(x-center)/scale
    mean=float(y.mean());weights=np.linalg.solve(z.T@z+np.eye(x.shape[1]),z.T@(y-mean))
    return dict(center=center.tolist(),scale=scale.tolist(),weights=weights.tolist(),intercept=mean,alpha=1.)


def score(rows,cuts,kind,model):
    if not rows:return dict(windows=0)
    x=xmatrix(rows,cuts,kind);y=np.array([r['move_bps'] for r in rows])
    pred=model['intercept']+((x-model['center'])/model['scale'])@np.array(model['weights'])
    denominator=float(((y-y.mean())**2).sum())
    return dict(windows=len(rows),rmse_bps=float(np.sqrt(np.mean((pred-y)**2))),
                zero_rmse_bps=float(np.sqrt(np.mean(y*y))),
                descriptive_r_squared=1-float(((pred-y)**2).sum())/denominator if denominator else None)


def mutual_information(x,y):
    counts=np.zeros((3,3))
    for a,b in zip(x,y):counts[int(np.sign(a))+1,int(np.sign(b))+1]+=1
    probabilities=counts/counts.sum();px=probabilities.sum(1);py=probabilities.sum(0)
    return float(sum(p*math.log2(p/(px[i]*py[j])) for i,row in enumerate(probabilities) for j,p in enumerate(row) if p))


def information_diagnostic(rows):
    y=np.array([r['move_bps'] for r in rows]);blocks={}
    for i,r in enumerate(rows):blocks.setdefault(r['start_ns']//(60*NS),[]).append(i)
    result={};rng=np.random.default_rng(148)
    for key in ('signed_btc','ofi_btc','display_pressure'):
        x=np.array([r[key] for r in rows]);observed=mutual_information(x,y)
        null=[];indices=list(blocks.values())
        if len(indices)>=10:
            for _ in range(200):
                reordered=np.concatenate([indices[j] for j in rng.permutation(len(indices))])
                null.append(mutual_information(x[reordered],y))
        result[key]=dict(empirical_bits=observed,block_shuffle_null_median_bits=float(np.median(null)) if null else None,
                         block_shuffle_null_95th_bits=float(np.quantile(null,.95)) if null else None,minute_blocks=len(indices))
    return result


def run(states_dir,raw_dir,out):
    out=Path(out);out.mkdir(parents=True,exist_ok=True);data={};audits={};hashes={}
    for hour in HOURS:
        bp=Path(states_dir)/f'BTCUSDT_orderbook_{hour}_observed_changes.csv';tp=Path(raw_dir)/f'BTCUSDT_trades_{hour}.parquet'
        reconstruction=json.loads(bp.with_suffix('.json').read_text())
        with bp.open() as handle:
            actual_rows=sum(1 for _ in csv.DictReader(handle))
        if actual_rows!=reconstruction['calibration_intervals']:
            raise ValueError(f'{hour}: CSV has {actual_rows} rows; reconstruction expected {reconstruction["calibration_intervals"]}')
        trades,missing,gaps=read_trade_observations(tp)
        data[hour],audits[hour]=build_windows(read_book(bp),trades,missing,gaps)
        audits[hour]['trade_id_gap_ranges']=len(gaps)
        audits[hour]['missing_trade_payload_records']=len(missing)
        audits[hour]['reconstruction']=reconstruction
        hashes[hour]={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in (bp,tp)}
        print(hour,audits[hour],flush=True)
    cuts=thresholds(data[HOURS[0]]);models={k:fit(data[HOURS[0]],cuts,k) for k in ('trade_only','book_only','joint')}
    reports={}
    for hour,rows in data.items():
        universe=[r['start_ns']//(60*NS) for r in rows];groups={}
        for r in rows:
            for name in categories(r,cuts):groups.setdefault(name,[]).append(r)
        fresh=[r for r in rows if r['fresh_250ms']]
        fresh_groups={}
        for r in fresh:
            for name in categories(r,cuts):fresh_groups.setdefault(name,[]).append(r)
        reports[hour]=dict(groups={k:describe(v,universe) for k,v in groups.items()},
                           fresh_sensitivity=describe(fresh,[r['start_ns']//(60*NS) for r in fresh]),
                           fresh_groups={k:describe(v,[r['start_ns']//(60*NS) for r in fresh]) for k,v in fresh_groups.items()},
                           fresh_regressions={k:score(fresh,cuts,k,m) for k,m in models.items()},
                           contrasts={f'{a}_minus_{b}':contrast(groups,universe,a,b) for a,b in
                                      (('book_agrees','book_opposes'),('display_reinforces','display_opposes'),('high_pressure_thin','high_pressure_deep'))},
                           fresh_contrasts={f'{a}_minus_{b}':contrast(fresh_groups,[r['start_ns']//(60*NS) for r in fresh],a,b) for a,b in
                                      (('book_agrees','book_opposes'),('display_reinforces','display_opposes'))},
                           block_length_sensitivity={str(seconds):contrast(groups,[r['start_ns']//(seconds*NS) for r in rows],
                                     'display_reinforces','display_opposes',seconds) for seconds in (30,120)},
                           regressions={k:score(rows,cuts,k,m) for k,m in models.items()},
                           information=information_diagnostic(rows))
        with (out/f'{hour}_windows.csv').open('w') as f:
            w=csv.DictWriter(f,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)
    result=dict(status='descriptive_ecology_research_not_causal_or_tradable',training_hour=HOURS[0],hours=list(HOURS),
                thresholds=cuts,features=list(FEATURES),models=models,audits=audits,input_sha256=hashes,results=reports,
                methods=dict(window='Approximately one second, disjoint interiors, post-state t0 to t1; book changes and trades use (t0,t1].',
                             ofi='Indicator-weighted changes of best bid/ask price and queue size, accumulated across received update bundles.',
                             confidence='1000 one-minute block bootstrap draws; conditional mean/probability intervals include zero-eligible observed minute blocks. Exploratory and not multiple-comparison adjusted.',
                             information='Three-state sign mutual information with 200 whole-minute-block shuffles. Exchangeability across minutes is unverified; this is not a causal or calibrated significance test.'),
                limitations=['Six selected discontinuous hours over two days, all previously inspected; no untouched final evaluation.',
                             'Anonymous L2 cannot identify makers, institutions, retail, informed traders, intent, cancellations separately from execution, or signed option inventory.',
                             'Batched L2 OFI is an observed quote-change statistic, not a complete sequence of individual order events.',
                             'Same-window book/OFI includes price-changing quotes: explanatory fit partly mechanical and not forward prediction.',
                             'Trade and book channels are aligned by receipt time, not proven matching-engine causal order; message clocks and delays can differ.',
                             'Near-touch changes use each update pre-midpoint; price-band movement and unknown deeper levels affect interpretation.',
                             'Thin/deep groups are not matched for trade size or volatility; pressure thresholds already normalize by depth, so group differences do not estimate a causal depth effect.',
                             'Forward means condition on observable endpoints and verified paths; missingness can bias their distributions.',
                             'Bootstrap intervals describe within-hour dependence under block assumptions, not across-day robustness or participant causality.',
                             'No fees, execution, profitability, policy promotion or historical-to-live venue transfer is implied.'])
    (out/'report.json').write_text(json.dumps(result,indent=2)+'\n');return result

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--states-dir',required=True);p.add_argument('--raw-dir',required=True);p.add_argument('--out',required=True);a=p.parse_args();run(a.states_dir,a.raw_dir,a.out)
