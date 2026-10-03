"""Receipt-time trade token adapter and causal book join; no execution attribution."""
import bisect,hashlib,json,math
from pathlib import Path
import numpy as np
import pyarrow.parquet as pq
from .book_changes import plain
from .observed_ecology_environment import load,examples
from .six_field_tokens import QuantileCodec,SixFieldTokenizer

def flow_interval(times,signed,start,end,missing=(),gap_ranges=()):
    if end<=start:raise ValueError('Invalid horizon')
    if any(start<t<=end for t in missing) or any(a<end and b>start for a,b in gap_ranges):return None
    lo=bisect.bisect_right(times,start);hi=bisect.bisect_right(times,end);s=signed[lo:hi];total=sum(abs(x) for x in s)
    return None if total==0 else sum(s)/total

def run(root,upload):
    root=Path(root);upload=Path(upload);paths=sorted((root/'data/processed/mechanics_study_states').glob('*_observed_changes.csv'))+sorted((root/'data/processed/mechanics_replication_states').glob('*_observed_changes.csv'));paths=sorted(paths);cutoff=json.loads((root/'docs/market_tokens/bitcoin_event_trial/RESULTS.json').read_text())['training_cutoff_ns'];reports=[];all_events=[];train_size=[];train_gap=[];train_times=[]
    for bp in paths:
        hour=bp.name.replace('BTCUSDT_orderbook_','').replace('_observed_changes.csv','');tp=upload/('BTCUSDT_trades_'+hour+'.parquet');source,tmp=plain(tp)
        try:d=pq.read_table(source,columns=['received_time','trade_time','trade_id','price','quantity','is_buyer_maker','order_type']).to_pydict()
        finally:
            if tmp:Path(source).unlink()
        rows=sorted(zip(*(d[k] for k in ('received_time','trade_time','trade_id','price','quantity','is_buyer_maker','order_type'))),key=lambda x:(x[0],x[2]));book=load(bp);bt=[b['received_time_ns'] for b in book];accepted=[];missing=[];gaps=[];validt=[];signed=[];counts=dict(raw=len(rows),future_timestamp=0,missing_payload=0,no_fresh_book=0,tied_receipts=0);prev=None
        for t,event,identity,p,q,maker,kind in rows:
            if prev is not None:
                if identity>prev[1]+1:gaps.append((prev[0],t))
                if t==prev[0]:counts['tied_receipts']+=1
            dt=None if prev is None else (t-prev[0])/1e9;prev=(t,identity);p=float(p);q=float(q)
            if p==q==0 and kind=='NA':missing.append(t);counts['missing_payload']+=1;continue
            if event*10**6>t:missing.append(t);counts['future_timestamp']+=1;continue
            if not math.isfinite(p+q) or min(p,q)<=0 or maker is None:raise ValueError('Invalid trade')
            validt.append(t);signed.append(q*(-1 if maker else 1));j=bisect.bisect_left(bt,t)-1
            if j<0 or t-bt[j]>250_000_000 or book[j]['post_best_bid']>=book[j]['post_best_ask'] or book[j]['event_time_ms']*10**6>bt[j]:counts['no_fresh_book']+=1;continue
            b=book[j];record=dict(receipt_ns=t,side='sell' if maker else 'buy',size=q,dt=dt,relative_price_bps=10000*math.log(p/b['post_mid']),reference_ns=bt[j]);accepted.append(record)
            if t<=cutoff and dt is not None:train_size.append(np.log1p(q));train_gap.append(np.log1p(dt));train_times.append(t)
        targets=[]
        for e in examples(book):
            value=flow_interval(validt,signed,e['decision_ns'],e['label']['target_end_ns'],missing,gaps)
            if value is not None:targets.append(dict(decision_ns=e['decision_ns'],label_available_ns=e['label']['target_end_ns'],signed_flow=value))
        reports.append(dict(hour=hour,counts=counts,book_joined_trades=len(accepted),trade_id_gap_ranges=len(gaps),flow_targets=len(targets),training_resolved_flow_targets=sum(x['label_available_ns']<=cutoff for x in targets),later_flow_targets=sum(x['decision_ns']>cutoff for x in targets),first_flow_target=targets[0] if targets else None,book_sha256=hashlib.sha256(bp.read_bytes()).hexdigest(),trade_sha256=hashlib.sha256(tp.read_bytes()).hexdigest()));all_events.extend(accepted)
    size=QuantileCodec(32).fit(train_size,train_times,cutoff);gap=QuantileCodec(32).fit(train_gap,train_times,cutoff);codec=SixFieldTokenizer(size,gap);later=sorted((x for x in all_events if x['receipt_ns']>cutoff),key=lambda x:x['receipt_ns']);sample=later[0];sample['tokens']=codec.encode('trade',sample['side'],None,sample['size'],sample['dt'],decision_ns=sample['receipt_ns'])
    result=dict(status='trade_token_and_flow_target_audit_not_trained_model',cutoff_ns=cutoff,training_codec_trades=len(train_times),vocabulary_size=codec.vocabulary_size,first_later_trade=sample,reports=reports,qualified=False,orders_enabled=False,limits=['Eight discontinuous recordings already inspected. Counted targets are not independent.','Trade aggressor is observed; participant identity and tick-level metadata remain missing. Relative price bps is retained numerically, not inserted as a fabricated tick token.','Strict preceding receipt book join, maximum 250ms age; no exchange execution-order identification.','Trade ID gaps and missing/future payload records invalidate intersecting flow targets; no-trade windows remain missing, not neutral flow.','Equal receipt times preserve trade-ID order; time gap may be zero. Cross-feed receipt ties use strictly preceding book only.','No neural flow training, trade-book attribution, stylized-fact generation, cost replay or live promotion.'])
    out=root/'docs/market_tokens/bitcoin_event_trial/TRADE_AUDIT.json';out.write_text(json.dumps(result,indent=2)+'\n');print(json.dumps({k:v for k,v in result.items() if k not in ('reports','limits')},indent=2));print('total joined trades',sum(x['book_joined_trades'] for x in reports),'later flow targets',sum(x['later_flow_targets'] for x in reports));return result
if __name__=='__main__':
    import sys
    run(sys.argv[1],sys.argv[2])
