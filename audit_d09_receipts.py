"""Reconcile canonical event-time trade sets with actual feature availability."""
from pathlib import Path
import argparse,json,hashlib
import numpy as np
import pyarrow.parquet as pq
from tokenizer_v1 import load_hours
from src.simulation.book_changes import plain

def interval_receipts(event_ms,receipt_ns,t0,t1):
    order=np.argsort(event_ms,kind='stable');event=np.asarray(event_ms)[order];receipt=np.asarray(receipt_ns,dtype=np.int64)[order];lo=np.searchsorted(event,t0,side='right');hi=np.searchsorted(event,t1,side='right');latest=np.array([int(receipt[a:b].max()) if b>a else 0 for a,b in zip(lo,hi)],dtype=np.int64)
    return hi-lo,latest,order,lo,hi

def run(root,upload):
    root=Path(root);upload=Path(upload);hours=load_hours(root);reports=[]
    for df in hours:
        hour=df['hour'].iloc[0];p=upload/('BTCUSDT_trades_'+hour+'.parquet');source,tmp=plain(p)
        try:d=pq.read_table(source,columns=['trade_time','received_time','quantity','is_buyer_maker']).to_pydict()
        finally:
            if tmp:Path(source).unlink()
        count,last,order,lo,hi=interval_receipts(np.array(d['trade_time']),np.array(d['received_time']),df['t0_event_time_ms'].values,df['t1_event_time_ms'].values);counts_ok=count==df['n_trades'].values;q=np.array(d['quantity'],float);maker=np.array(d['is_buyer_maker']);cs=np.r_[0,np.cumsum(q[order]*np.where(maker[order],-1,1))];flows=cs[hi]-cs[lo];flow_ok=np.isclose(flows,df['signed_flow_qty'].values,atol=1e-6,rtol=1e-6);book=df['received_time_ns'].values.astype(np.int64);availability=np.maximum(book,last);delay=(availability-book)/1e6;late=last>book
        decisions=[];already=[];eligible=0
        ep=df['episode_id'].values;times=df['t1_event_time_ms'].values;ix=df['interval_index'].values
        for j in range(15,len(df)-10,10):
            a=j-15;b=j+10
            if len(set(ep[a:b+1]))!=1 or np.any(np.diff(times[a:b+1])<=0) or np.any(np.diff(ix[a:b+1])!=1):continue
            eligible+=1;decision=int(availability[a:j+1].max());decisions.append(decision);already.append(book[b]<=decision)
        reports.append(dict(hour=hour,intervals=len(df),future_trade_event_at_receipt=int((np.array(d['trade_time'],dtype=np.int64)*10**6>np.array(d['received_time'],dtype=np.int64)).sum()),zero_quantity_trade_records=int((q==0).sum()),trade_count_mismatch=int((~counts_ok).sum()),signed_flow_mismatch=int((~flow_ok).sum()),late_trade_intervals=int(late.sum()),late_trade_fraction=float(late.mean()),feature_delay_ms_quantiles={str(x):float(np.quantile(delay,x)) for x in (.5,.9,.99,1)},future_book_event_at_receipt=int((df['t1_event_time_ms'].values*10**6>book).sum()),model_eligible_contexts=eligible,ten_event_target_already_available_at_feature_decision=int(sum(already)),raw_trade_sha256=hashlib.sha256(p.read_bytes()).hexdigest()))
    result=dict(status='canonical_trade_set_receipt_reconciliation',qualified=False,orders_enabled=False,reports=reports,all_counts_match=all(x['trade_count_mismatch']==0 for x in reports),all_signed_flow_match=all(x['signed_flow_mismatch']==0 for x in reports),correction='D09B contains receipt timestamps and the tokenizer join retains them. Plain D09 lacks latest contributing trade receipt, reconstructed here.',limits=['Not a full live or sequence-validity qualification. Canonical sets can contain missing raw payloads; audit separately.','Max contributing receipt is offline provenance; knowing a set is complete online also requires an explicit watermark/buffering rule.','Price-target start must move to the valid book available at decision time before executable training; merely changing the timestamp is insufficient.','Context receipt maxima must be used; event-time context may not arrive in event-time order.','Endpoint stride restarts per hour; eligibility counts differ slightly from the prior concatenated model sample phase.','No new model trained or larger pretrained weights installed in this audit.'])
    out=root/'docs/market_tokens/d09_trial/RECEIPT_AUDIT.json';out.write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2));return result
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--repo',default='.');p.add_argument('--upload',required=True);a=p.parse_args();run(a.repo,a.upload)
