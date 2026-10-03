"""Training-only typed state tokens. No sequence predictor or trading promotion."""
from collections import deque
import hashlib,json,math
from pathlib import Path
import numpy as np
from .ecology_tree_research import inputs,FEATURE_NAMES
from .observed_ecology_environment import load,examples
BOS,EOS,GAP=0,1,2
FIELDS=FEATURE_NAMES+['past_mid_return_bps']

def frame(row,previous=None):
    return inputs(row)+[10000*math.log(row['post_mid']/previous['post_mid']) if previous else 0.]

def fit_tokenizer(x,bins=16):
    x=np.asarray(x,dtype=float)
    if x.ndim!=2 or x.shape[1]!=8 or not len(x) or not np.isfinite(x).all():raise ValueError('Invalid training values')
    if bins<2:raise ValueError('At least two bins required')
    return dict(bins=bins,fields=FIELDS,cuts=np.quantile(x,np.arange(1,bins)/bins,axis=0).T.tolist(),lower=x.min(axis=0).tolist(),upper=x.max(axis=0).tolist(),special={'BOS':BOS,'EOS':EOS,'GAP':GAP},vocabulary_size=3+8*(bins+2))

def encode_frame(x,m):
    x=np.asarray(x,dtype=float)
    if x.shape!=(8,) or not np.isfinite(x).all():raise ValueError('Invalid observation')
    width=m['bins']+2;ids=[]
    for f,value in enumerate(x):
        bucket=0 if value<m['lower'][f] else width-1 if value>m['upper'][f] else 1+int(np.searchsorted(m['cuts'][f],value,side='right'))
        ids.append(3+f*width+bucket)
    return ids

def valid(row):
    return row['event_time_ms']*10**6<=row['received_time_ns'] and row['post_best_bid']<row['post_best_ask'] and row['post_bid_depth_10bps']+row['post_ask_depth_10bps']>0

def contexts(rows,m,length=32,max_gap_ns=250_000_000):
    if length<1:raise ValueError('Positive context length required')
    history=deque(maxlen=length);previous=None
    for r in rows:
        if not valid(r):history.clear();previous=None;continue
        if previous is not None and (r['episode']!=previous['episode'] or not 0<r['received_time_ns']-previous['received_time_ns']<=max_gap_ns):history.clear();previous=None
        history.append((r['received_time_ns'],encode_frame(frame(r,previous),m)));previous=r
        if len(history)==length:
            yield dict(start_ns=history[0][0],end_ns=history[-1][0],episode=r['episode'],tokens=[BOS]+[t for _,frame in history for t in frame]+[EOS])

def audit(root):
    root=Path(root);paths=sorted((root/'data/processed/mechanics_study_states').glob('*_observed_changes.csv'))+sorted((root/'data/processed/mechanics_replication_states').glob('*_observed_changes.csv'));first=next(p for p in paths if '2026-05-25_00' in p.name);raw=load(first);labeled=examples(raw);cut=labeled[len(labeled)//2]['decision_ns'];training=[r for r in raw if r['received_time_ns']<=cut and valid(r)]
    values=[];previous=None
    for row in raw:
        if row['received_time_ns']>cut:break
        if not valid(row):previous=None;continue
        if previous is not None and (row['episode']!=previous['episode'] or not 0<row['received_time_ns']-previous['received_time_ns']<=250_000_000):previous=None
        values.append(frame(row,previous));previous=row
    m=fit_tokenizer(values);reports=[]
    for path in paths:
        raw=load(path);n=out=0;sample=None
        for c in contexts(raw,m):
            if c['end_ns']<=cut:continue
            n+=1;out+=any((token-3)%(m['bins']+2) in (0,m['bins']+1) for token in c['tokens'][1:-1]);sample=sample or c
        reports.append(dict(file=path.name,overlapping_contexts=n,contexts_with_range_exceedance=out,first_context=sample,input_sha256=hashlib.sha256(path.read_bytes()).hexdigest()))
    result=dict(status='token_encoder_and_context_audit_only',predictor_trained=False,qualified=False,training_observations=len(training),cutoff_ns=cut,context_frames=32,tokens_per_context=258,tokenizer=m,reports=reports,limits=['Typed displayed-book state tokens, not identified individual order messages or trader types.','All source recordings previously inspected; contexts overlap heavily and counts are not independent samples.','No label is encoded. Quantization loses numeric precision; original numeric observations and targets remain necessary.','No transformer training, next-event generation, forecast evaluation, paper PnL or live deployment performed.','Only receipt-time continuity, event-not-future and book-order validity checked; not every live eligibility condition.'])
    out=root/'docs/market_tokens';out.mkdir(parents=True,exist_ok=True);(out/'ENCODER_AUDIT.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(dict(training_observations=len(training),vocabulary=m['vocabulary_size'],contexts=sum(r['overlapping_contexts'] for r in reports),predictor_trained=False)))
    return result
if __name__=='__main__':
    import sys
    audit(sys.argv[1])
