"""State-conditional observed event/quantity calibration, separate from trading."""
import argparse
import csv
import hashlib
import json
from pathlib import Path
from .book_change_rates import fit as count_fit,score as count_score,bucket,KINDS
from .strategy_research import HOURS

QUANTITIES=('bid_add_qty','bid_remove_qty','ask_add_qty','ask_remove_qty')

def read(path):
    with Path(path).open(newline='') as handle:
        raw=list(csv.DictReader(handle))
        if any(None in r or any(v is None for v in r.values()) for r in raw):raise ValueError('Incomplete replay row')
        return [{k:float(v) for k,v in row.items() if k not in ('received_time_ns','event_time_ms','episode')} for row in raw]

def fit(rows):
    model=count_fit(rows)
    seconds=model['training_exposure_seconds'];prior=model['prior_exposure_seconds']
    global_rates={k:sum(r[k] for r in rows)/seconds for k in QUANTITIES}
    groups={name:dict(seconds=0.,**{k:0. for k in QUANTITIES}) for name in model['state_rates']}
    for r in rows:
        name=bucket(r['pre_obi_top'],r['pre_bid_depth_10bps']+r['pre_ask_depth_10bps'],model['depth_cutoffs_btc'])
        g=groups[name];g['seconds']+=r['exposure_seconds']
        for k in QUANTITIES:g[k]+=r[k]
    model['global_quantity_btc_per_second']=global_rates
    model['state_quantity_btc_per_second']={name:{k:(g[k]+prior*global_rates[k])/(g['seconds']+prior) for k in QUANTITIES} for name,g in groups.items()}
    model['warning']='Observed displayed-level change rates and quantities; no identification of orders, cancellations, participants, FIFO fills, psychological states or fitted Hawkes excitation.'
    return model

def score(rows,model):
    result=count_score(rows,model);seconds=result['holdout_exposure_seconds']
    observed={k:0. for k in QUANTITIES};predicted={k:0. for k in QUANTITIES}
    for r in rows:
        name=bucket(r['pre_obi_top'],r['pre_bid_depth_10bps']+r['pre_ask_depth_10bps'],model['depth_cutoffs_btc'])
        for k in QUANTITIES:
            observed[k]+=r[k]
            predicted[k]+=model['state_quantity_btc_per_second'][name][k]*r['exposure_seconds']
    result['quantity_rates']={k:dict(observed_btc_per_second=observed[k]/seconds,
                     conditional_predicted_btc_per_second=predicted[k]/seconds,
                     constant_predicted_btc_per_second=model['global_quantity_btc_per_second'][k]) for k in QUANTITIES}
    c=result['poisson_nll_per_exposure_second'];result['conditional_count_improvement_pct']=100*(1-c['conditional']/c['constant']) if c['constant'] else None
    return result

def run(book_dir,out):
    datasets={};hashes={}
    for hour in HOURS:
        path=Path(book_dir)/f'BTCUSDT_orderbook_{hour}_observed_changes.csv'
        datasets[hour]=read(path);hashes[path.name]=hashlib.sha256(path.read_bytes()).hexdigest()
    model=fit(datasets[HOURS[0]])
    result=dict(status='exploratory_calibration_not_live_promoted',training_hour=HOURS[0],model=model,
                input_sha256=hashes,scores={h:dict(role='train' if h==HOURS[0] else 'previously_inspected_later_hour',**score(rows,model)) for h,rows in datasets.items()},
                limits=['Four discontinuous previously inspected hours do not establish cross-regime calibration.',
                        'Poisson counts are a diagnostic likelihood; updates bundle multiple changed levels and can be overdispersed.',
                        'Near-touch changes are measured against the pre-update midpoint, not private order identities.',
                        'Receipt delay and verified-episode censoring remain unresolved.',
                        'Binance historical parameters are not deployed on the Kraken live feed.'])
    out=Path(out);out.parent.mkdir(parents=True,exist_ok=True);out.write_text(json.dumps(result,indent=2)+'\n');return result

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--book-dir',type=Path,required=True);p.add_argument('--out',type=Path,required=True);a=p.parse_args();r=run(a.book_dir,a.out)
    print(json.dumps({h:s['conditional_count_improvement_pct'] for h,s in r['scores'].items()},indent=2))
