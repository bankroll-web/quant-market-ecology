"""Training-only displayed-liquidity response benchmark; no actor inference."""
import csv,hashlib,json,math
from pathlib import Path
import numpy as np
from .ecology_regime_dynamics import state

TRAINING='2026-05-25_00'
FIELDS=('bid_added_btc','bid_reduced_btc','ask_added_btc','ask_reduced_btc')


def enrich(row,cut):
    depth=float(row['start_depth_btc'])
    if depth<=0:raise ValueError('Nonpositive depth')
    values={k:float(row[k]) for k in FIELDS}
    if any(not math.isfinite(x) or x<0 for x in values.values()):raise ValueError('Invalid displayed quantity')
    bid=values['bid_added_btc']-values['bid_reduced_btc'];ask=values['ask_added_btc']-values['ask_reduced_btc']
    pressure=(bid-ask)/depth
    if not math.isclose(pressure,float(row['display_pressure']),abs_tol=1e-9):raise ValueError('Display-pressure reconciliation failed')
    signed=float(row['signed_btc']);trade=float(row['trade_pressure'])
    if not math.isclose(signed/depth,trade,abs_tol=1e-9):raise ValueError('Trade-pressure reconciliation failed')
    label=state(dict(signed_btc=signed,trade_pressure=trade,display_pressure=pressure),cut)
    direction=1 if signed>0 else -1 if signed<0 else 0
    # Buy: bid changes support pressure; ask changes resist it. Sell: reversed.
    support=bid if direction>0 else ask if direction<0 else None
    resistance=ask if direction>0 else bid if direction<0 else None
    return dict(regime=label,fresh=row['fresh_250ms']=='True',direction=direction,
        metrics={**{k.replace('_btc','_per_start_depth'):v/depth for k,v in values.items()},
                 'gross_turnover_per_start_depth':sum(values.values())/depth,
                 'aligned_display_pressure':direction*pressure,
                 'support_side_net_per_start_depth':support/depth if support is not None else None,
                 'resistance_side_net_per_start_depth':resistance/depth if resistance is not None else None,
                 'same_window_move_bps':float(row['move_bps'])})


def describe(rows):
    if not rows:return dict(windows=0,metrics={})
    result={}
    for k in rows[0]['metrics']:
        a=[r['metrics'][k] for r in rows if r['metrics'][k] is not None]
        result[k]=dict(count=len(a),quantiles=dict(zip(('p10','p50','p90'),map(float,np.quantile(a,[.1,.5,.9]))))) if a else dict(count=0,quantiles=None)
    return dict(windows=len(rows),metrics=result)


def build(windows,reference,out):
    if TRAINING not in Path(windows).name:raise ValueError('Training hour only')
    ref=json.loads(Path(reference).read_text())
    if ref['training_hour']!=TRAINING:raise ValueError('Reference training mismatch')
    expected=ref['input_sha256'].get(TRAINING)
    actual=hashlib.sha256(Path(windows).read_bytes()).hexdigest()
    if expected is None or expected!=actual:raise ValueError('Frozen training input hash mismatch')
    with Path(windows).open() as f:rows=[enrich(r,ref['pressure_cut']) for r in csv.DictReader(f)]
    groups={}
    for fresh in (False,True):
        selected=[r for r in rows if r['fresh']] if fresh else rows
        groups['fresh' if fresh else 'all']={s:describe([r for r in selected if r['regime']==s]) for s in ref['states']}
    result=dict(status='training_liquidity_benchmark_not_agent_calibration',training_hour=TRAINING,pressure_cut=ref['pressure_cut'],input_sha256=actual,groups=groups,
        limitations=['Anonymous L2 changes cannot identify market makers, institutions or retail traders.',
        'Displayed reductions combine executions, cancellations and receipt aggregation; do not feed these alongside trades as independent cancellation events.',
        'Quantities use observed moving near-touch bands and are not total venue order arrival sizes.',
        'Regimes and price moves are classified over the same window; these are descriptive associations, not pre-trade predictors or causal effects.',
        'Gross turnover can greatly exceed starting depth because quotes repeatedly change within a window.',
        'Quantiles are empirical training summaries, without independent validation or uncertainty intervals.'])
    Path(out).write_text(json.dumps(result,indent=2)+'\n');return result
