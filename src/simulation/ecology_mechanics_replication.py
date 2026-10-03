"""Apply a frozen descriptive ecology study to additional historical recordings."""
import argparse
import csv
import hashlib
import json
from pathlib import Path
import math
import numpy as np
from . import ecology_price_mechanics as study
from .mechanics_input_audit import audit

BASELINE_SHA256='0fce731298694ce20b8ee626e02728fd56cc6744fc2aee090eca49f60be6d15c'
HOURS=('2026-05-26_03','2026-05-26_09')
IMPLEMENTATION_SHA256={'ecology_price_mechanics.py':'377bd045efe8f80b12c04778d3a9fe41bf9dc2eb369f3a8f7d3fd85f97744b42',
                       'book_changes.py':'84516859a7a7b58d177e70523d531af9180dbf03ea443e16705c695b9f1f1f43'}


def load_frozen(path):
    payload=Path(path).read_bytes()
    if hashlib.sha256(payload).hexdigest()!=BASELINE_SHA256:raise ValueError('Frozen baseline changed; do not refit against replication')
    for name,expected in IMPLEMENTATION_SHA256.items():
        if hashlib.sha256(Path(__file__).with_name(name).read_bytes()).hexdigest()!=expected:raise ValueError('Frozen observation implementation changed')
    baseline=json.loads(payload)
    if set(HOURS)&set(baseline['hours']):raise ValueError('Replication periods overlap baseline study')
    return baseline


def book_fit_diagnostic(rows,model):
    x=np.array([r['ofi_pressure'] for r in rows]);y=np.array([r['move_bps'] for r in rows])
    prediction=model['intercept']+(x-model['center'][0])/model['scale'][0]*model['weights'][0]
    error=(prediction-y)**2;count=max(1,math.ceil(.01*len(rows)));total=float(error.sum())
    worst=[]
    for i in np.argsort(error)[-3:][::-1]:
        detail={k:rows[int(i)][k] for k in ('start_ns','end_ns','episode','start_top_depth_btc','ofi_btc','ofi_pressure','move_bps','fresh_250ms')}
        detail['frozen_explanatory_fit_bps']=float(prediction[i]);worst.append(detail)
    return dict(ofi_pressure_mean=float(x.mean()),ofi_pressure_std=float(x.std()),training_ofi_pressure_std=model['scale'][0],
                largest_absolute_ofi_pressure=float(np.max(np.abs(x))),worst_one_percent_windows=count,
                worst_one_percent_squared_error_fraction=float(np.sort(error)[-count:].sum()/total) if total else None,
                worst_windows=worst,interpretation='Post-result diagnostic only. All windows remain in primary scores; no clipping, exclusion, refitting or model promotion.')


def run(baseline_path,books_dir,trades_dir,states_dir,out):
    baseline=load_frozen(baseline_path);out=Path(out);out.mkdir(parents=True,exist_ok=True)
    source_audit=audit(trades_dir,books_dir,states_dir,HOURS);reports={};quality={};hashes={}
    for hour in HOURS:
        book=Path(states_dir)/f'BTCUSDT_orderbook_{hour}_observed_changes.csv'
        tape=study.read_book(book)
        if len(tape)!=source_audit[hour]['reconstruction']['calibration_intervals']:raise ValueError('Reconstruction row-count mismatch')
        trades_path=Path(trades_dir)/f'BTCUSDT_trades_{hour}.parquet'
        trades,missing,gaps=study.read_trade_observations(trades_path)
        rows,quality[hour]=study.build_windows(tape,trades,missing,gaps)
        if not rows:raise ValueError(f'{hour}: no eligible observed windows')
        cuts=baseline['thresholds'];models=baseline['models'];groups={};fresh_groups={}
        for row in rows:
            for name in study.categories(row,cuts):
                groups.setdefault(name,[]).append(row)
                if row['fresh_250ms']:fresh_groups.setdefault(name,[]).append(row)
        fresh=[row for row in rows if row['fresh_250ms']];universe=[r['start_ns']//(60*study.NS) for r in rows]
        fresh_universe=[r['start_ns']//(60*study.NS) for r in fresh]
        pairs=(('book_agrees','book_opposes'),('display_reinforces','display_opposes'),('high_pressure_thin','high_pressure_deep'))
        reports[hour]=dict(groups={k:study.describe(v,universe) for k,v in groups.items()},
                           fresh_groups={k:study.describe(v,fresh_universe) for k,v in fresh_groups.items()},
                           contrasts={a+'_minus_'+b:study.contrast(groups,universe,a,b) for a,b in pairs},
                           fresh_contrasts={a+'_minus_'+b:study.contrast(fresh_groups,fresh_universe,a,b) for a,b in pairs},
                           block_length_sensitivity={str(s):study.contrast(groups,[r['start_ns']//(s*study.NS) for r in rows],'display_reinforces','display_opposes',s) for s in (30,120)},
                           regressions={k:study.score(rows,cuts,k,v) for k,v in models.items()},
                           fresh_regressions={k:study.score(fresh,cuts,k,v) for k,v in models.items()},
                           book_fit_failure_diagnostic=book_fit_diagnostic(rows,models['book_only']),
                           information=study.information_diagnostic(rows))
        with (out/f'{hour}_windows.csv').open('w') as handle:
            writer=csv.DictWriter(handle,fieldnames=list(rows[0]));writer.writeheader();writer.writerows(rows)
        hashes[hour]=hashlib.sha256(book.read_bytes()).hexdigest()
        print(hour,quality[hour],flush=True)
    result=dict(status='frozen_additional_period_replication_not_untouched_final_test',baseline_commit='cd587f84e104c2149f50ebd1ab71fb103b0c1160',
                baseline_sha256=BASELINE_SHA256,implementation_sha256=IMPLEMENTATION_SHA256,hours=list(HOURS),training_hour=baseline['training_hour'],
                thresholds=baseline['thresholds'],models=baseline['models'],audits=quality,source_audit=source_audit,
                processed_book_sha256=hashes,results=reports,methods=baseline['methods'],
                limitations=baseline['limitations']+['These are additional hours from the same two-day archive, not additional contiguous days. Earlier project work may have inspected them; untouched status is not established.',
                    '09:00 book comes from a legacy CSV export. Decimal update IDs are safely cast without float inference, but CSV precision or provenance lost before this export cannot be restored.'])
    conversion=Path(books_dir)/'BTCUSDT_orderbook_2026-05-26_09.conversion.json'
    result['csv_conversion']=json.loads(conversion.read_text())
    (out/'report.json').write_text(json.dumps(result,indent=2)+'\n');return result


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--baseline',required=True);p.add_argument('--books-dir',required=True);p.add_argument('--trades-dir',required=True);p.add_argument('--states-dir',required=True);p.add_argument('--out',required=True);a=p.parse_args()
    run(a.baseline,a.books_dir,a.trades_dir,a.states_dir,a.out)
