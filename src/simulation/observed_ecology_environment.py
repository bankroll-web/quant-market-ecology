"""Immutable observed paths with past-only observations; no counterfactual fills."""
import bisect,csv,hashlib,json,math
from pathlib import Path
import numpy as np
from .forecast_evaluation import gate_inputs,gate_training,score

FEATURES=('post_mid','post_best_bid','post_best_ask','post_spread','post_obi_top','post_bid_depth_10bps','post_ask_depth_10bps','best_quote_ofi_btc','bid_add_qty','bid_remove_qty','ask_add_qty','ask_remove_qty')


def load(path):
    with Path(path).open() as f:
        rows=[{k:int(r[k]) for k in ('received_time_ns','event_time_ms','episode')}|{k:float(r[k]) for k in FEATURES} for r in csv.DictReader(f)]
    if any(b['received_time_ns']<=a['received_time_ns'] for a,b in zip(rows,rows[1:])):raise ValueError('State receipts must increase')
    return rows


def examples(rows,horizon_ns=10**9,max_gap_ns=250_000_000):
    times=[r['received_time_ns'] for r in rows];bad=[0]
    for i in range(1,len(rows)):
        bad.append(bad[-1]+int(rows[i]['episode']!=rows[i-1]['episode'] or times[i]-times[i-1]>max_gap_ns))
    result=[];next_decision=-1
    for i,r in enumerate(rows):
        t=times[i]
        if t<next_decision:continue
        next_decision=t+horizon_ns
        j=bisect.bisect_left(times,t+horizon_ns,i+1)
        if j>=len(rows) or times[j]-t-horizon_ns>max_gap_ns or bad[j]!=bad[i]:continue
        if any(rows[k]['post_best_bid']>=rows[k]['post_best_ask'] for k in range(i,j+1)):continue
        gate_inputs(t,[dict(event_ns=r['event_time_ms']*10**6,available_ns=t)])
        result.append(dict(decision_ns=t,observation={k:r[k] for k in FEATURES},
            label=dict(target_end_ns=times[j],label_available_ns=times[j],return_bps=10000*math.log(rows[j]['post_mid']/r['post_mid']))))
    return result


class ObservedEnvironment:
    """Step returns only the current receipt observation. Labels are separate."""
    def __init__(self,examples):self._examples=examples;self.index=0
    def reset(self):self.index=0
    def step(self):
        if self.index>=len(self._examples):raise StopIteration
        row=self._examples[self.index];self.index+=1
        return dict(decision_ns=row['decision_ns'],observation=dict(row['observation']))


def benchmark(paths,out):
    if not paths or '2026-05-25_00' not in str(paths[0]):raise ValueError('Training path must be first')
    datasets=[examples(load(p)) for p in paths]
    first=datasets[0]
    if len(first)<20:raise ValueError('Insufficient training examples')
    cutoff=first[len(first)//2]['decision_ns']
    train=[r for r in first if r['label']['label_available_ns']<=cutoff]
    gate_training(cutoff,[r['label'] for r in train])
    returns=[r['label']['return_bps'] for r in train]
    p=sum(x>0 for x in returns)/len(returns);lower,upper=map(float,np.quantile(returns,[.1,.9]))
    reports={}
    for path,data in zip(paths,datasets):
        evaluation=[r for r in data if r['decision_ns']>cutoff]
        if not evaluation:raise ValueError('Empty evaluation')
        targets=[r['label']['return_bps'] for r in evaluation]
        reports[Path(path).stem]=dict(examples=len(evaluation),frozen_base_rate=score([p]*len(targets),targets,[(lower,upper)]*len(targets)),coin_probability=score([.5]*len(targets),targets,[(lower,upper)]*len(targets)),
            zero_return_fraction=sum(x==0 for x in targets)/len(targets))
    result=dict(status='observed_path_baseline_not_trading_policy',training_examples=len(train),training_cutoff_ns=cutoff,positive_probability=p,interval_80_bps=[lower,upper],reports=reports,
        input_sha256={Path(p).name:hashlib.sha256(Path(p).read_bytes()).hexdigest() for p in paths},
        limitations=['Only recorded paths, no counterfactual participant response or queue fills.',
        'Features contain completed past receipt bundles, not future-window totals.',
        'Targets use the first valid receipt at or after one second, with maximum 250ms sampling lag.',
        'Decisions are spaced by at least one second; target sampling lag can create overlapping outcomes. Counts are not independent sample sizes.',
        'Base rate and interval fit only first-half training-hour resolved labels. All recordings have previously been inspected; these are development comparisons, not untouched validation.',
        'No costs, PnL, ML training or live strategy qualification performed. Brier scores are not trading returns.'])
    Path(out).write_text(json.dumps(result,indent=2)+'\n');return result
