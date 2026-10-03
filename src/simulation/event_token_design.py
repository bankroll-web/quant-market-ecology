"""Causal event vocabulary and available-at multi-scale joins; no inferred identities."""
from dataclasses import dataclass
import math
import numpy as np

KINDS=('trade','add','cancel','book_change','unknown')
SIDES=('buy','sell','bid','ask','unknown')
SCALES=('tick','minute','daily','regime')

@dataclass(frozen=True)
class Event:
    event_ns:int
    available_ns:int
    kind:str
    side:str
    price:float
    reference_mid:float
    size:float
    reference_available_ns:int
    episode:str
    participant_cluster:str='unknown'
    participant_model_available_ns:int|None=None


def measurements(event,previous=None):
    if event.kind not in KINDS or event.side not in SIDES:raise ValueError('Unknown schema category')
    if event.event_ns>event.available_ns or event.reference_available_ns>event.available_ns:raise ValueError('Future event or reference')
    if not all(math.isfinite(v) for v in (event.price,event.reference_mid,event.size)) or min(event.price,event.reference_mid)<=0 or event.size<0:raise ValueError('Invalid numerical event')
    if event.participant_cluster!='unknown' and (event.participant_model_available_ns is None or event.participant_model_available_ns>event.available_ns):raise ValueError('Cluster must have a causal fitted model timestamp')
    if previous is not None and (previous.episode!=event.episode or previous.available_ns>=event.available_ns):raise ValueError('Reset context across episodes or non-increasing availability')
    gap=None if previous is None else (event.available_ns-previous.available_ns)/1e9
    return [10000*math.log(event.price/event.reference_mid),math.log1p(event.size),None if gap is None else math.log1p(gap)]


def fit(events,training_cutoff_ns,bins=16):
    """Reject mixed training/future input rather than silently fitting all records."""
    if bins<2 or not events:raise ValueError('Training events and >=2 bins required')
    values=[];previous=None
    for event in events:
        if event.available_ns>training_cutoff_ns:raise ValueError('Tokenizer leakage: event beyond training cutoff')
        if previous is not None and previous.episode!=event.episode:previous=None
        values.append(measurements(event,previous));previous=event
    specifications=[]
    for column in zip(*values):
        observed=np.array([x for x in column if x is not None])
        specifications.append(None if not len(observed) else {'cuts':np.quantile(observed,np.arange(1,bins)/bins).tolist(),'lower':float(observed.min()),'upper':float(observed.max())})
    return {'version':1,'bins':bins,'training_cutoff_ns':training_cutoff_ns,'fields':specifications,'size_unit':'caller-defined base quantity; never mix contracts without normalization','participant_semantics':'estimated cluster, never verified retail/institution identity'}


def encode(event,tokenizer,previous=None):
    values=measurements(event,previous);result=['scale:tick','type:'+event.kind,'side:'+event.side]
    for name,value,spec in zip(('relative_price_bps','log_size','log_gap_seconds'),values,tokenizer['fields']):
        if value is None or spec is None:bucket='missing'
        elif value<spec['lower']:bucket='under'
        elif value>spec['upper']:bucket='over'
        else:bucket=str(int(np.searchsorted(spec['cuts'],value,side='right')))
        result.append(name+':'+bucket)
    result.append('participant_estimate:'+event.participant_cluster)
    return result


def available_scales(decision_ns,frames):
    """Latest completed, received frame per scale. No nearest/future joins."""
    result={}
    for frame in frames:
        scale=frame['scale']
        if scale not in SCALES:raise ValueError('Unknown scale')
        if frame['period_end_ns']>frame['available_ns']:raise ValueError('Frame available before completion')
        if frame['available_ns']<=decision_ns and (scale not in result or (frame['period_end_ns'],frame['available_ns'])>(result[scale]['period_end_ns'],result[scale]['available_ns'])):result[scale]=frame
    return result


def promotion_gate(evidence):
    required=('timing_audit','tokenizer_audit','heldout_fidelity','fat_tails','volatility_clustering','flow_memory','cost_latency_replay','baseline_comparison','feature_ablation','trial_registry','multiple_testing_adjustment','fresh_forward_test')
    missing=[key for key in required if evidence.get(key) is not True]
    return {'qualified':not missing,'missing':missing,'orders_enabled':False}
