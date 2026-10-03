"""Exact-price receipt-window allocation audit, not identification of cancellations."""
import bisect,csv,hashlib,json,math
from collections import Counter,defaultdict
from pathlib import Path
import pyarrow.parquet as pq
from .book_changes import grouped,plain,state
from .ecology_price_mechanics import read_trade_observations

TRAINING='2026-05-25_00'


def allocate(reductions,trades):
    """Cap a candidate execution allocation by both observed net loss and trades.

    Keys are (passive book side, exact price). A trade can enter only one bucket.
    Unexplained net loss is deliberately not named cancellation.
    """
    if any(not math.isfinite(v) or v<0 for d in (reductions,trades) for v in d.values()):raise ValueError('Invalid quantities')
    matched={k:min(q,trades.get(k,0.)) for k,q in reductions.items()}
    return dict(reduction=sum(reductions.values()),candidate_execution=sum(matched.values()),
                unexplained_reduction=sum(q-matched[k] for k,q in reductions.items()),
                unmatched_trade=sum(q-matched.get(k,0.) for k,q in trades.items()))


def receipt_slice(times,start,end):
    if end<=start:raise ValueError('Invalid receipt interval')
    # Both boundaries are excluded; end ties are counted separately.
    return bisect.bisect_right(times,start),bisect.bisect_left(times,end)


def trade_tape(path):
    # Reuse the established payload and gap audit, then retain prices and tape order.
    _,missing,gaps=read_trade_observations(path);source,tmp=plain(path)
    try:
        d=pq.read_table(source,columns=['received_time','price','quantity','is_buyer_maker']).to_pydict()
        rows=sorted([(int(t),'bid' if maker else 'ask',float(p),float(q)) for t,p,q,maker in zip(*(d[k] for k in ('received_time','price','quantity','is_buyer_maker'))) if float(q)>0],key=lambda x:x[0])
    finally:
        if tmp:Path(source).unlink()
    return rows,missing,gaps


def audit(book_path,trade_path,windows_path,reference,out):
    ref=json.loads(Path(reference).read_text())
    if ref['training_hour']!=TRAINING or any(TRAINING not in Path(p).name for p in (book_path,trade_path,windows_path)):raise ValueError('Training hour only')
    window_hash=hashlib.sha256(Path(windows_path).read_bytes()).hexdigest()
    if window_hash!=ref['input_sha256'][TRAINING]:raise ValueError('Frozen window hash mismatch')
    with Path(windows_path).open() as f:windows=list(csv.DictReader(f))
    trades,missing,gaps=trade_tape(trade_path);times=[r[0] for r in trades]
    bids={};asks={};valid=False;waiting=False;sequence=None;snapshot_id=None;previous=None;episode=0
    intervals=[];quality=Counter()
    for key,levels in grouped(book_path):
        kind,t=key[:2]
        if kind=='snapshot':
            bids={p:q for s,p,q in levels if s=='bid' and q>0};asks={p:q for s,p,q in levels if s=='ask' and q>0}
            sequence=snapshot_id=key[3];waiting=True;valid=False;previous=None;continue
        U,u,pu=key[4:7]
        if waiting:
            if u<=snapshot_id:continue
            if not U<=snapshot_id+1<=u:valid=False;waiting=False;bids={};asks={};continue
            waiting=False;valid=True;episode+=1;bridge=True
        elif not valid:continue
        elif pu!=sequence:valid=False;bids={};asks={};previous=None;quality['sequence_failures']+=1;continue
        else:bridge=False
        mid=state(bids,asks)[0];reductions={};adds=0.
        for side,p,q in levels:
            target=bids if side=='bid' else asks;old=target.get(p,0.)
            near=(side=='bid' and p>=mid*.999) or (side=='ask' and p<=mid*1.001)
            if near:
                if q<old:reductions[(side,p)]=reductions.get((side,p),0.)+old-q
                else:adds+=q-old
            if q<=0:target.pop(p,None)
            else:target[p]=q
        sequence=u
        if not bridge and previous is not None and t>previous:
            a,b=receipt_slice(times,previous,t)
            observed=trades[a:b];buckets=defaultdict(float)
            for _,side,p,q in observed:buckets[(side,p)]+=q
            result=allocate(reductions,buckets)
            ties=trades[b:bisect.bisect_right(times,t)]
            result.update(start_ns=previous,end_ns=t,episode=episode,added=adds,tied_trade_btc=sum(r[3] for r in ties),tied_trade_count=len(ties),interval_trade_btc=sum(r[3] for r in observed),
                source_gap=any(x<t and y>previous for x,y in gaps) or any(previous<x<=t for x in missing))
            intervals.append(result)
        previous=t
    ends=[r['end_ns'] for r in intervals];totals=Counter();per_window=[]
    for w in windows:
        a,b=int(w['start_ns']),int(w['end_ns']);selected=intervals[bisect.bisect_right(ends,a):bisect.bisect_right(ends,b)]
        if not selected or selected[0]['start_ns']!=a or selected[-1]['end_ns']!=b or any(y['start_ns']!=x['end_ns'] for x,y in zip(selected,selected[1:])) or any(r['episode']!=int(w['episode']) or r['start_ns']<a or r['end_ns']-r['start_ns']>250_000_000 or r['source_gap'] for r in selected):raise ValueError('Accepted window boundary mismatch')
        expected=float(w['bid_reduced_btc'])+float(w['ask_reduced_btc']);observed=sum(r['reduction'] for r in selected)
        if not math.isclose(expected,observed,abs_tol=1e-7):raise ValueError('Near-touch reduction reconciliation failed')
        additions=sum(r['added'] for r in selected)
        if not math.isclose(additions,float(w['bid_added_btc'])+float(w['ask_added_btc']),abs_tol=1e-7):raise ValueError('Addition reconciliation failed')
        values={k:sum(r[k] for r in selected) for k in ('reduction','candidate_execution','unexplained_reduction','unmatched_trade','interval_trade_btc','tied_trade_btc','tied_trade_count')}
        if not math.isclose(values['interval_trade_btc']+values['tied_trade_btc'],float(w['absolute_btc']),abs_tol=1e-7):raise ValueError('Trade quantity reconciliation failed')
        totals.update(values);per_window.append(dict(start_ns=a,end_ns=b,**values))
    result=dict(status='receipt_order_candidate_allocation_not_cancellation_identification',training_windows=len(windows),totals=dict(totals),quality=dict(quality),windows=per_window,
        input_sha256={Path(p).name:hashlib.sha256(Path(p).read_bytes()).hexdigest() for p in (book_path,trade_path,windows_path,reference)},
        assumptions=['Only exact-price passive-side trades received strictly after the preceding valid L2 receipt and strictly before the current L2 receipt are candidates.',
        'Trades tied with a book receipt are excluded from allocation; cross-stream arrival order at equal timestamps is unknown.',
        'Per-price allocation is capped at min(net displayed reduction, candidate trade quantity); each trade enters one interval only.',
        'This allocation is a bookkeeping scenario, not a proven lower or upper bound on executions: net updates can hide simultaneous additions and removals, and feeds may arrive in different orders.',
        'Unexplained reduction is not labeled cancellation; unmatched trades include coverage, replenishment, lag and aggregation effects.',
        'Books remain authoritative absolute L2 updates; trades are not applied a second time. No new generative maker policy or profitable strategy is installed.'])
    Path(out).write_text(json.dumps(result,indent=2)+'\n');return result
