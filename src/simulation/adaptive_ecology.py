"""Past-only exposure-clock EWMA baseline; no trading policy or paper reproduction."""
import argparse
import csv
import hashlib
import json
import math
from pathlib import Path
from .ecology_calibration import read, fit, QUANTITIES
from .book_change_rates import bucket
from .strategy_research import HOURS


class AdaptiveRates:
    def __init__(self, initial, half_life_seconds=30.):
        if not math.isfinite(half_life_seconds) or half_life_seconds <= 0:
            raise ValueError('positive finite half life required')
        self.initial = dict(initial)
        self.half_life = half_life_seconds
        self.reset()

    def reset(self):
        self.rates = dict(self.initial)

    def update(self, quantities, exposure):
        if not math.isfinite(exposure) or exposure <= 0:
            raise ValueError('positive finite exposure required')
        if any(not math.isfinite(quantities[k]) or quantities[k] < 0 for k in self.rates):
            raise ValueError('finite nonnegative quantities required')
        weight = -math.expm1(-math.log(2) * exposure / self.half_life)
        self.rates = {k:(1-weight)*v+weight*quantities[k]/exposure for k,v in self.rates.items()}


def evaluate(rows, model, half_life=30.):
    initial = model['global_quantity_btc_per_second']
    adaptive = AdaptiveRates(initial, half_life)
    methods = ('constant','conditional','adaptive_constant','adaptive_conditional')
    observed = {k:0. for k in QUANTITIES}
    predicted = {m:{k:0. for k in QUANTITIES} for m in methods}
    absolute = {m:{k:0. for k in QUANTITIES} for m in methods}
    states = {}
    previous_end = previous_episode = None
    resets = 0
    seconds = 0.
    for r in rows:
        dt = r['exposure_seconds']
        if not math.isfinite(dt) or dt <= 0:
            raise ValueError('invalid interval exposure')
        end = r['received_time_ns']; start = end-round(dt*1e9)
        if previous_end is not None and end <= previous_end:
            raise ValueError('unordered observations')
        if previous_episode != r['episode'] or previous_end is None or abs(start-previous_end)>1000:
            adaptive.reset(); resets += 1
        name = bucket(r['pre_obi_top'],r['pre_bid_depth_10bps']+r['pre_ask_depth_10bps'],model['depth_cutoffs_btc'])
        state = states.setdefault(name,dict(observed={k:0. for k in QUANTITIES},
                                           predicted={m:{k:0. for k in QUANTITIES} for m in methods}))
        # Rates are fixed BEFORE consuming this interval's observed quantities.
        for k in QUANTITIES:
            q = r[k]
            if not math.isfinite(q) or q < 0:raise ValueError('invalid quantity')
            conditional = model['state_quantity_btc_per_second'][name][k]
            scale = adaptive.rates[k]/initial[k] if initial[k] else 1.
            rates = dict(constant=initial[k],conditional=conditional,
                         adaptive_constant=adaptive.rates[k],adaptive_conditional=conditional*scale)
            observed[k] += q; state['observed'][k] += q
            for method,rate in rates.items():
                expected=rate*dt
                predicted[method][k]+=expected;state['predicted'][method][k]+=expected
                absolute[method][k]+=abs(expected-q)
        adaptive.update(r,dt)  # Only affects subsequent predictions.
        seconds += dt; previous_end=end;previous_episode=r['episode']
    return dict(exposure_seconds=seconds,resets=resets,intervals=len(rows),
                observed_btc=observed,predicted_btc=predicted,
                interval_quantity_wape_pct={m:{k:100*v/observed[k] if observed[k] else None for k,v in vals.items()} for m,vals in absolute.items()},
                state_total_quantity_wape_pct={m:{k:100*sum(abs(s['predicted'][m][k]-s['observed'][k]) for s in states.values())/observed[k] if observed[k] else None for k in QUANTITIES} for m in methods})


def load(path):
    rows=read(path)
    with Path(path).open() as handle:raw=list(csv.DictReader(handle))
    for r,meta in zip(rows,raw):
        r['episode']=int(meta['episode']);r['received_time_ns']=int(meta['received_time_ns'])
    return rows


def run(directory, output):
    paths={h:Path(directory)/f'BTCUSDT_orderbook_{h}_observed_changes.csv' for h in HOURS}
    data={h:load(p) for h,p in paths.items()}
    model=fit(data[HOURS[0]])
    result=dict(status='exploratory_not_promoted',training_hour=HOURS[0],half_life_verified_seconds=30,
                formula='rate_next=(1-a)*rate_previous+a*observed_qty/exposure; a=1-exp(-ln(2)*exposure/30)',
                input_sha256={h:hashlib.sha256(p.read_bytes()).hexdigest() for h,p in paths.items()},
                scores={h:evaluate(rows,model) for h,rows in data.items()},
                limitations=['Fixed 30-second half life chosen before this run, not optimized; inspected recordings remain exploratory.',
                             'Exposure duration is known only at interval end: this evaluates past-only rates over observed exposure, not an executable interval quantity forecast.',
                             'Adaptation uses verified exposure time and resets at episode changes and gaps; it is not a Hawkes model.',
                             'Activity-level adaptation cannot identify participants, validate uncertainty intervals or establish trading profitability.',
                             'No Binance parameters transferred to Coinbase and no live policy changed.'])
    Path(output).write_text(json.dumps(result,indent=2)+'\n')
    return result

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--book-dir',required=True);p.add_argument('--out',required=True);a=p.parse_args()
    r=run(a.book_dir,a.out)
    print(json.dumps({h:s['state_total_quantity_wape_pct'] for h,s in r['scores'].items()},indent=2))
