"""Daily development reconstruction and smoothed token-bigram baseline audit."""
from pathlib import Path
import json,hashlib
import numpy as np
from .crossasset_daily_research import load
from .six_field_tokens import QuantileCodec
CUT=int(np.datetime64('2024-10-01','ns').astype(np.int64))
def run(root):
    root=Path(root);dates,ns,ix,x,y,opens=load(root);tr=ns[ix+3]<=CUT;ev=np.array(['2025-01-01'<=dates[i+2]<='2026-08-30' for i in ix]);available=ns[ix+1];fitmask=available<=CUT
    # Every fit is frozen at the initial training boundary. No evaluation bin tuning.
    classes=np.searchsorted(np.quantile(y[tr],np.arange(1,9)/9),y,side='right');prior=(np.bincount(classes[tr],minlength=9)+1)/(tr.sum()+9);reports={}
    for bins in (16,32,64):
        codecs=[QuantileCodec(bins).fit(x[fitmask,col],available[fitmask],CUT) for col in (0,1,2,3)];tokens=codecs[0].encode(x[:,0]);conditional={}
        for j in np.flatnonzero(tr):
            if j==0:continue
            key=(int(tokens[j-1]),int(tokens[j]));conditional.setdefault(key,np.ones(9));conditional[key][classes[j]]+=1
        predictions=[];backoff=0
        for j in np.flatnonzero(ev):
            counts=conditional.get((int(tokens[j-1]),int(tokens[j])))
            if counts is None:predictions.append(prior);backoff+=1
            else:predictions.append(counts/counts.sum())
        p=np.array(predictions);truth=classes[ev]
        reports[str(bins)]={'fields':{name:c.audit(x[fitmask,col],x[ev,col]) for name,col,c in zip(('return_bps','log_quote_volume','parkinson_variance','amihud_illiquidity'),(0,1,2,3),codecs)},'two_state_token_context_return_class_log_loss':float(-np.log(p[np.arange(len(truth)),truth]).mean()),'prior_log_loss':float(-np.log(prior[truth]).mean()),'unseen_context_backoff_fraction':backoff/len(truth),'observed_training_contexts':len(conditional)}
    result={'status':'daily_development_tokenizer_audit_not_event_training','training_cutoff_ns':CUT,'evaluation_days':int(ev.sum()),'comparisons':reports,'selected_bins':None,'qualified':False,'limits':['Periods already examined. Three bin variants are recorded experiments, not untouched tests.','Daily four-field reconstruction is not event size/gap reconstruction; no event-level tick size or participant labels inferred.','Two-state token baseline predicts return classes, not generated order messages. No PnL or costs evaluated.','No rolling refit in this frozen comparison. Rolling codec API requires a fresh version per decision and only past observations.','Frequency divergence and numeric error use different units per field; neither alone selects a tradable tokenizer.'],'data_audit_sha256':hashlib.sha256((root/'docs/crossasset_daily/DATA_AUDIT.json').read_bytes()).hexdigest()}
    out=root/'docs/market_tokens/SIX_FIELD_AUDIT.json';out.write_text(json.dumps(result,indent=2)+'\n');print(json.dumps({b:{k:v for k,v in r.items() if k!='fields'} for b,r in reports.items()},indent=2));return result
if __name__=='__main__':
    import sys
    run(sys.argv[1])
