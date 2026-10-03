"""Bounded background research fitting on directly received Coinbase features."""
from collections import deque
from bisect import bisect_left
from concurrent.futures import ThreadPoolExecutor
from .coinbase_training import dataset_records,train_examples


def merge_examples(previous, incoming, limit=20000):
    """Retain audited labels once; changing raw-buffer start cannot duplicate trials."""
    merged={r['decision_ns']:r for r in previous}
    times=sorted(merged)
    for row in sorted(incoming,key=lambda r:r['decision_ns']):
        key=row['decision_ns']
        i=bisect_left(times,key)
        if (i and key-times[i-1]<1_000_000_000) or (i<len(times) and times[i]-key<1_000_000_000):continue
        merged[key]=row;times.insert(i,key)
    return [merged[t] for t in sorted(merged)[-limit:]]


def fit_snapshot(records, previous):
    incoming=dataset_records(records)
    examples=merge_examples(previous,incoming)
    report=train_examples(examples)
    report.update(usable_examples=len(examples),latest_buffer_examples=len(incoming))
    return report,examples


class LiveTraining:
    def __init__(self):
        self.records=deque(maxlen=20000);self.generation=0;self.venue=None;self.future=None;self.last_attempt=None
        self.pool=ThreadPoolExecutor(max_workers=1,thread_name_prefix='research-fit')
        self.report=dict(status='collecting',qualified=False,usable_examples=None)
        self.examples=[];self.venue_epoch=0
    def record(self,kind,payload):
        if kind in ('coinbase_disconnect','kraken_disconnect'):self.generation+=1
        if kind in ('coinbase_model_observation','kraken_model_observation'):
            venue=(payload['provider'],payload['symbol'])
            if self.venue is not None and venue!=self.venue:
                self.records.clear();self.examples=[];self.venue_epoch+=1;self.generation+=1;self.report=dict(status='venue_changed_collecting',qualified=False)
            self.venue=venue
            self.records.append(dict(payload,session=str(self.generation)))
    def status(self,now_ns):
        if self.future is not None and self.future.done():
            try:
                result,examples=self.future.result()
                if self.future_epoch==self.venue_epoch:
                    self.report=result;self.examples=examples
            except Exception as error:self.report=dict(status='training_error',qualified=False,error=type(error).__name__+': '+str(error))
            self.future=None
        if self.future is None and (self.last_attempt is None or now_ns-self.last_attempt>=60_000_000_000):
            self.last_attempt=now_ns;self.future_epoch=self.venue_epoch;records=list(self.records)
            self.future=self.pool.submit(fit_snapshot,records,list(self.examples))
        return dict(self.report,buffered_feature_bundles=len(self.records),buffer_limit=20000,
                    fitting=self.future is not None,orders_enabled=False,signal='WAIT',
                    audited_example_limit=20000,
                    caveat='Accumulated venue-specific development fit; repeated evaluation is not untouched validation. Reset on venue change or process restart. No profitable policy qualification.')
