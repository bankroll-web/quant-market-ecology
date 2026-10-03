"""Bounded background research fitting on directly received Coinbase features."""
from collections import deque
from concurrent.futures import ThreadPoolExecutor
from .coinbase_training import dataset_records,train_examples


class LiveTraining:
    def __init__(self):
        self.records=deque(maxlen=20000);self.generation=0;self.future=None;self.last_attempt=None
        self.pool=ThreadPoolExecutor(max_workers=1,thread_name_prefix='research-fit')
        self.report=dict(status='collecting',qualified=False,usable_examples=None)
    def record(self,kind,payload):
        if kind=='coinbase_disconnect':self.generation+=1
        if kind=='coinbase_model_observation':self.records.append(dict(payload,session=str(self.generation)))
    def status(self,now_ns):
        if self.future is not None and self.future.done():
            try:self.report=self.future.result()
            except Exception as error:self.report=dict(status='training_error',qualified=False,error=type(error).__name__+': '+str(error))
            self.future=None
        if self.future is None and (self.last_attempt is None or now_ns-self.last_attempt>=60_000_000_000):
            self.last_attempt=now_ns;records=list(self.records)
            self.future=self.pool.submit(lambda:train_examples(dataset_records(records)))
        return dict(self.report,buffered_feature_bundles=len(self.records),buffer_limit=20000,
                    fitting=self.future is not None,orders_enabled=False,signal='WAIT',
                    caveat='Rolling same-session development fit; no untouched-day or profitable paper policy qualification. Reset on process restart.')
