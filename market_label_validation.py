"""Receipt-clock quote labels and chronological purging. Research utilities only."""
import math

def triple_barrier(quotes,decision_ns,deadline_ns,profit_bps,loss_bps,*,side='long',latency_ns=0,roundtrip_fee_bps=0,max_gap_ns=250_000_000):
    """First received quote at/after latency is an entry proxy. Never invent fills.

    quotes: ordered dictionaries with time_ns, bid, ask, segment.
    Use only causal thresholds determined before decision_ns. Long enters ask,
    exits bid; short enters bid, exits ask. Fee is a stated roundtrip scenario.
    Requires same continuous segment through outcome and coverage of time exit.
    """
    if side not in ('long','short') or deadline_ns<=decision_ns or min(profit_bps,loss_bps)<=0 or latency_ns<0 or roundtrip_fee_bps<0 or max_gap_ns<=0:raise ValueError('Invalid policy')
    def valid(q):return all(math.isfinite(q[k]) for k in ('bid','ask')) and 0<q['bid']<=q['ask']
    if any(b['time_ns']<=a['time_ns'] for a,b in zip(quotes,quotes[1:])):raise ValueError('Quotes must be strictly receipt-ordered')
    eligible=[i for i,q in enumerate(quotes) if q['time_ns']>=decision_ns+latency_ns]
    def censored(reason):return dict(status='censored',reason=reason,label=None)
    if not eligible:return censored('missing_entry')
    i=eligible[0];entry=quotes[i]
    if entry['time_ns']>=deadline_ns or entry['time_ns']-(decision_ns+latency_ns)>max_gap_ns or not valid(entry):return censored('invalid_or_late_entry')
    price=entry['ask'] if side=='long' else entry['bid'];last=entry
    def net(q):
        exit_price=q['bid'] if side=='long' else q['ask']
        return (10000*math.log(exit_price/price) if side=='long' else 10000*math.log(price/exit_price))-roundtrip_fee_bps
    def done(q,label,reason,available):return dict(status='observed',label=label,reason=reason,entry_ns=entry['time_ns'],outcome_ns=q['time_ns'],label_available_ns=available,event_start_ns=decision_ns,event_end_ns=available,net_log_bps=net(q),fill_model='received_top_quote_proxy_not_actual_fill')
    for q in quotes[i+1:]:
        if q['segment']!=entry['segment'] or q['time_ns']-last['time_ns']>max_gap_ns or not valid(q):return censored('gap_reset_or_invalid_quote')
        if q['time_ns']>deadline_ns:
            if deadline_ns-last['time_ns']>max_gap_ns:return censored('stale_time_exit')
            return done(last,0,'time_barrier',q['time_ns'])
        value=net(q)
        if value>=profit_bps:return done(q,1,'profit_barrier',q['time_ns'])
        if value<=-loss_bps:return done(q,-1,'loss_barrier',q['time_ns'])
        last=q
        if q['time_ns']==deadline_ns:return done(q,0,'time_barrier',q['time_ns'])
    return censored('missing_deadline_coverage')

def purged_walk_forward(events,test_indices,*,embargo_ns=0):
    """Past-only training; purge closed information intervals overlapping test.

    Events contain start_ns/end_ns; start may include causal feature history.
    Embargo extends test intervals after their end; mainly relevant to future
    training in other designs. Here future rows are always excluded.
    """
    if embargo_ns<0 or not test_indices:raise ValueError('Invalid split')
    if any(e['end_ns']<e['start_ns'] for e in events):raise ValueError('Invalid event interval')
    tests=[events[i] for i in test_indices];cutoff=min(e['start_ns'] for e in tests);excluded=set(test_indices);train=[]
    for i,e in enumerate(events):
        if i in excluded or e['start_ns']>=cutoff:continue
        if any(e['start_ns']<=t['end_ns']+embargo_ns and e['end_ns']>=t['start_ns'] for t in tests):continue
        train.append(i)
    return train,list(test_indices)
