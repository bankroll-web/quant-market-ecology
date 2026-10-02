"""Bounded exploratory horizon/regime study; no market-ready strategy claim."""
import argparse
import hashlib
import json
from pathlib import Path
import numpy as np
from .strategy_research import HOURS,NS,load,fit,predict,paper

HORIZONS=(1,5,15,30,60)
LATENCIES_MS=(100,500)
COSTS=(5.,10.)
GATES=('all','high_flow','high_obi','thin','deep','flow_obi_agree')
BASES=('flow_follow','flow_reverse','obi_follow','obi_reverse')
MISSING_EXIT_STRESS_BPS=50.


def thresholds(train):
    x=np.array([r['x'] for r in train])
    return dict(flow=float(np.quantile(abs(x[:,0]),.75)),
                obi=float(np.quantile(abs(x[:,1]),.75)),
                depth_low=float(np.quantile(x[:,5],.25)),depth_high=float(np.quantile(x[:,5],.75)))


def signals(name,rows,cuts,models,cost=5.):
    if name=='no_trade':return np.zeros(len(rows),dtype=int)
    if not rows:return np.array([],dtype=int)
    x=np.array([r['x'] for r in rows])
    if name in models:
        prediction=predict(models[name],rows)
        # Current spread is a further conservative gate, not a forecast of exit spread.
        return np.where(abs(prediction)>cost+x[:,4],np.sign(prediction),0).astype(int)
    base,gate=name.split(':')
    sign=np.sign(x[:,0] if base.startswith('flow') else x[:,1])
    if base.endswith('reverse'):sign=-sign
    mask={'all':np.ones(len(rows),dtype=bool),'high_flow':abs(x[:,0])>=cuts['flow'],
          'high_obi':abs(x[:,1])>=cuts['obi'],'thin':x[:,5]<=cuts['depth_low'],
          'deep':x[:,5]>=cuts['depth_high'],
          'flow_obi_agree':np.sign(x[:,0])*np.sign(x[:,1])>0}[gate]
    return np.where(mask,sign,0).astype(int)


def block_interval(rows,actions,cost=5.):
    """One-minute blocks with empty eligible blocks retained; exploratory only."""
    blocks={}
    for row,action in zip(rows,actions):
        block=row['decision_ns']//(60*NS)
        blocks.setdefault(block,[])
        blocks[block].append(0. if not action else (row['long_quote_bps'] if action>0 else row['short_quote_bps'])-cost)
    # Resample sums and opportunity counts jointly, preserving within-block dependence.
    counts=np.array([len(values) for values in blocks.values()])
    sums=np.array([sum(values) for values in blocks.values()])
    if len(counts)<10:return dict(blocks=len(counts),lower=None,upper=None,note='Too few observed minute blocks')
    rng=np.random.default_rng(117);indices=rng.integers(0,len(counts),size=(2000,len(counts)))
    means=sums[indices].sum(1)/counts[indices].sum(1)
    return dict(blocks=len(counts),lower=float(np.quantile(means,.025)),upper=float(np.quantile(means,.975)),
                note='Exploratory within-hour block bootstrap per resolved opportunity; no adjustment for 260 candidates, censoring, longer dependence or regime changes')


def evaluate(rows,unresolved,actions,unknown_actions,cost):
    result=paper(rows,actions,cost)
    missing=int(np.count_nonzero(unknown_actions))
    result.update(unresolved_opened_trades=missing,
                  stress_50bps_sum=result['summed_net_bps']-missing*MISSING_EXIT_STRESS_BPS,
                  stress_10bps_sum=result['summed_net_bps']-missing*10.,
                  mean_net_per_resolved_opportunity_bps=result['summed_net_bps']/len(rows) if rows else None)
    return result


def run(flow_dir,book_dir,out):
    configurations=[];provenance={}
    for hour in HOURS:
        paths=[Path(flow_dir)/f'{hour}_all_messages.csv',Path(book_dir)/f'BTCUSDT_orderbook_{hour}_observed_changes.csv']
        provenance[hour]={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in paths}
    for horizon in HORIZONS:
        for latency in LATENCIES_MS:
            data={};audits={}
            for hour in HOURS:
                data[hour],audits[hour]=load(Path(flow_dir)/f'{hour}_all_messages.csv',Path(book_dir)/f'BTCUSDT_orderbook_{hour}_observed_changes.csv',horizon*NS,latency*1_000_000,True)
            if len(data[HOURS[0]])<10:
                configurations.append(dict(horizon_seconds=horizon,latency_ms=latency,status='insufficient_training',audits={h:{k:v for k,v in a.items() if k!='unresolved'} for h,a in audits.items()}));continue
            cuts=thresholds(data[HOURS[0]])
            models={kind:fit(data[HOURS[0]],kind) for kind in ('ridge','rbf_kernel_ridge')}
            names=['no_trade']+[base+':'+gate for base in BASES for gate in GATES]+list(models)
            scores={}
            for name in names:
                hours={}
                for hour,rows in data.items():
                    unknown=audits[hour]['unresolved'];hour_scores={}
                    for cost in COSTS:
                        actions=signals(name,rows,cuts,models,cost);unknown_actions=signals(name,unknown,cuts,models,cost)
                        hour_scores[str(cost)]=evaluate(rows,unknown,actions,unknown_actions,cost)
                    hours[hour]=hour_scores
                scores[name]=hours
            # Choose only on the validation hour. Abstain unless the selected policy
            # has >=5 observed trades and beats zero under the missing-exit stress.
            eligible=[n for n in names if n!='no_trade' and scores[n][HOURS[1]]['5.0']['trades']>=5]
            winner=max(eligible,key=lambda n:scores[n][HOURS[1]]['5.0']['stress_50bps_sum'],default='no_trade')
            if scores[winner][HOURS[1]]['5.0']['stress_50bps_sum']<=0:winner='no_trade'
            intervals={h:block_interval(data[h],signals(winner,data[h],cuts,models)) for h in HOURS[1:]}
            oracle={h:dict(rows=len(rows),positive_after_5bps=sum(max(r['long_quote_bps'],r['short_quote_bps'])>5. for r in rows),
                         optimistic_sum_bps=sum(max(0.,r['long_quote_bps']-5.,r['short_quote_bps']-5.) for r in rows)) for h,rows in data.items()}
            configurations.append(dict(horizon_seconds=horizon,latency_ms=latency,status='exploratory',training_thresholds=cuts,
                selected_on_validation=winner,selected_block_intervals=intervals,
                oracle_diagnostic=oracle,audits={h:{k:v for k,v in a.items() if k!='unresolved'} for h,a in audits.items()},scores=scores))
            print(f'{horizon}s / {latency}ms: {winner}',flush=True)
    valid=[c for c in configurations if c['status']=='exploratory']
    # Across-horizon selection also uses only validation results, never later hours.
    selected=max(valid,key=lambda c:c['scores'][c['selected_on_validation']][HOURS[1]]['5.0']['stress_50bps_sum']) if valid else None
    summary=dict(status='not_qualified',candidate_count=len(valid)*26,selection_rule='Validation equal-unit net bps under 50bps missing-exit stress; at least five resolved validation trades. No-trade if nonpositive. Different horizons have different coverage, so ranking is exploratory.',
                 selected_configuration=dict(horizon_seconds=selected['horizon_seconds'],latency_ms=selected['latency_ms'],policy=selected['selected_on_validation']) if selected else None,
                 input_sha256=provenance,configurations=configurations,
                 limits=['Previously inspected four hours; adaptive reuse and 260 candidate comparisons make this development research, not pristine validation.',
                         'One-minute intervals are not multiple-testing-adjusted and do not resolve censoring or between-day uncertainty.',
                         'Missing-exit stress values are hypothetical scenarios, not measured losses or guaranteed worst-case bounds.',
                         'Bid/ask paper proxies lack order-size, queue, fill, impact, funding and liquidation modeling.',
                         'Oracle uses future prices and is an optimistic opportunity diagnostic, never a deployable policy.',
                         'Training quantiles use only label-resolved training rows and may inherit censoring selection bias.',
                         'No historical policy is promoted into the Kraken spot live system.'])
    out=Path(out);out.mkdir(parents=True,exist_ok=True);(out/'report.json').write_text(json.dumps(summary,indent=2)+'\n')
    return summary

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--flow-dir',type=Path,required=True);p.add_argument('--book-dir',type=Path,required=True);p.add_argument('--out',type=Path,required=True);a=p.parse_args();r=run(a.flow_dir,a.book_dir,a.out);print(json.dumps({k:v for k,v in r.items() if k!='configurations'},indent=2))
