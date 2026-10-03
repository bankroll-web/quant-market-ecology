"""Training-only contiguous trade-block driver; not a validated market model."""
import bisect,csv,hashlib,json,math,random
from pathlib import Path
from .ecology_price_mechanics import read_trade_observations
from .ecology_regime_dynamics import contiguous,summarize
from .ecology_calibration_check import ObservedBook,compare
from .ecology import common_flow
from .book_changes import plain
import pyarrow.parquet as pq


def load_pool(windows,tape):
    _,missing,gaps=read_trade_observations(tape)
    source,temporary=plain(tape)
    try:
        d=pq.read_table(source,columns=['received_time','quantity','is_buyer_maker']).to_pydict()
        trades=sorted([(int(t),float(q)*(-1 if maker else 1)) for t,q,maker in zip(d['received_time'],d['quantity'],d['is_buyer_maker']) if float(q)>0],key=lambda x:x[0])
    finally:
        if temporary:Path(source).unlink()
    times=[t[0] for t in trades];pool=[]
    with Path(windows).open() as f:raw=list(csv.DictReader(f))
    for row in raw:
        a,b=int(row['start_ns']),int(row['end_ns'])
        if any(a<t<=b for t in missing) or any(x<b and y>a for x,y in gaps):raise ValueError('Missing trade data')
        selected=trades[bisect.bisect_right(times,a):bisect.bisect_right(times,b)]
        if len(selected)!=int(row['trade_count']) or not math.isclose(sum(t[1] for t in selected),float(row['signed_btc']),abs_tol=1e-9) or not math.isclose(sum(abs(t[1]) for t in selected),float(row['absolute_btc']),abs_tol=1e-9):raise ValueError('Trade reconciliation failed')
        pool.append(dict(start_ns=a,end_ns=b,episode=int(row['episode']),duration_seconds=float(row['duration_seconds']),trades=[('buy' if q>0 else 'sell',abs(q)) for _,q in selected]))
    if not pool or any(b['start_ns']<a['end_ns'] for a,b in zip(pool,pool[1:])):raise ValueError('Empty or overlapping pool')
    return pool


def sample(pool,seed,steps=120,max_block=10):
    if not pool or steps<1 or max_block<1:raise ValueError('Invalid sampling parameters')
    rng=random.Random(seed);flow=[];source=[];block=0
    while len(flow)<steps:
        i=rng.randrange(len(pool));block+=1
        for offset in range(max_block):
            j=i+offset
            if j>=len(pool) or (offset and not contiguous(pool[j-1],pool[j])):break
            flow.append(list(pool[j]['trades']));source.append(dict(training_window=j,block=block,source_start_ns=pool[j]['start_ns'],source_end_ns=pool[j]['end_ns'],source_duration_seconds=pool[j]['duration_seconds']))
            if len(flow)==steps:break
    return flow,source


def simulate_prefix(params,flow):
    """Original normal rules before the forced second-120 intervention."""
    book=ObservedBook(params);rows=[]
    for second,trades in enumerate(flow):
        book.begin_observation(second);book.cancel('maker_A',.002);book.cancel('maker_B',.002)
        for side,qty in trades:
            filled,_=book.execute(side,qty)
            if not math.isclose(filled,qty,abs_tol=1e-9):raise ValueError(f'Unfilled flow at step {second}')
        book.replenish('maker_A',.08);book.replenish('maker_B',.08)
        rows.append(dict(book.state(second,'normal_liquidity'),start_ns=second*10**9,end_ns=(second+1)*10**9,episode=1,duration_seconds=1.))
    return rows


def check(config,reference,windows,tape,out):
    ref=json.loads(Path(reference).read_text());params=json.loads(Path(config).read_text())['calibration_from_valid_samples']
    if ref['training_hour']!='2026-05-25_00' or any('2026-05-25_00' not in Path(p).name for p in (windows,tape)):raise ValueError('Only frozen training hour permitted')
    pool=load_pool(windows,tape);reports={}
    for seed in (7,19,43):
        empirical,source=sample(pool,seed)
        for name,flow in [('assumed',common_flow(params,seed)[:120]),('empirical',empirical)]:
            rows=simulate_prefix(params,flow);summary,_,_=summarize(rows,ref['pressure_cut'])
            reports[f'{seed}_{name}']=dict(summary=summary,comparisons={h:compare(summary,r['summary']) for h,r in ref['results'].items()},provenance=source if name=='empirical' else None)
    result=dict(status='exploratory_training_driver_not_qualified',training_windows=len(pool),max_block_windows=10,steps=120,reports=reports,input_sha256={Path(p).name:hashlib.sha256(Path(p).read_bytes()).hexdigest() for p in (config,reference,windows,tape)},limitations=['Only training-hour trades sampled; later recordings were not used to fit or tune this driver.','Recorded 1–1.25 second windows map to one synthetic second; intra-window arrivals are not simulated.','Blocks stop at gaps; random block joins are artificial. Synthetic transition statistics include these joins and are descriptive.','Maker rules remain assumed; historical executions submitted as synthetic orders do not establish a causal counterfactual.','All comparison recordings were inspected previously; no untouched validation or profitable policy established.'])
    Path(out).write_text(json.dumps(result,indent=2)+'\n');return result
