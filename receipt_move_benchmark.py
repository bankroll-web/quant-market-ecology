"""Development-only, receipt-clock Bitcoin move benchmark with matched inputs.

Run: python receipt_move_benchmark.py --repo . --upload ../upload
No live orders, promotion or claims of untouched evaluation are made here.
"""
import argparse
from bisect import bisect_left, bisect_right, insort
from collections import deque
import json
from pathlib import Path
import time

import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.metrics import accuracy_score, brier_score_loss, log_loss, roc_auc_score
from receipt_tokens import load_receipt_hours

VERSION = 'receipt-move-matched-v3'
HORIZONS_MS = (100, 1000, 10000)
CONTEXT = 4
WARMUP = 16
MAX_GAP_NS = 250_000_000
BIN_COUNT = 16
DEPTH_WINDOW = 256
FEATURES = ('obi_post','spread_bps','bid_depth_percentile','ask_depth_percentile',
    'depth_in_prior_trades','dt_ms','ntr','signed_flow','total_flow',
    'bid_add','bid_remove','ask_add','ask_remove','mid_change_bps',
    'book_rate_10','book_rate_50','book_rate_200',
    'trade_rate_10','trade_rate_50','trade_rate_200','since_move_ms',
    'momentum_50_bps','momentum_200_bps','vol_50_bps','vol_200_bps','response_50_relative',
    'flow_1s','flow_10s','flow_60s','trades_1s','trades_10s','trades_60s',
    'vol_1s_bps','vol_10s_bps','vol_60s_bps')


def prior_percentile(values, window=DEPTH_WINDOW, minimum=WARMUP):
    """Rank current value in strictly prior trailing observations, ties midrank."""
    ordered=[];history=deque();result=np.full(len(values),np.nan)
    for i,value in enumerate(values):
        if len(ordered)>=minimum and np.isfinite(value):
            result[i]=(bisect_left(ordered,value)+bisect_right(ordered,value))/(2*len(ordered))
        if np.isfinite(value):
            insort(ordered,float(value));history.append(float(value))
            if len(history)>window:ordered.pop(bisect_left(ordered,history.popleft()))
    return result


def receipt_segments(full):
    """No ordering repairs: reject invalid receipt/event rows and continuity gaps."""
    n=len(full);receipt=full.decision_receipt_ns.to_numpy(dtype=np.int64)
    event=full.t1_event_time_ms.to_numpy(dtype=np.int64)*1_000_000
    episode=full.episode_id.to_numpy();hour=full.hour.to_numpy();ix=full.interval_index.to_numpy()
    mid=full.mid_t1.to_numpy(dtype=float)
    post_ok=np.zeros(n,bool)
    post_ok[:-1]=((hour[:-1]==hour[1:])&(episode[:-1]==episode[1:])&(ix[1:]==ix[:-1]+1)
        &(full.t1_event_time_ms.to_numpy()[:-1]==full.t0_event_time_ms.to_numpy()[1:])
        &np.isclose(mid[:-1],full.mid_t0.to_numpy()[1:],rtol=0,atol=1e-8))
    valid=full.receipt_valid.to_numpy(bool)&post_ok&(receipt>=event)&(receipt-event<=MAX_GAP_NS)
    valid &= np.isfinite(mid)&(mid>0)
    for column in ('bid_depth5_t0','ask_depth5_t0'):
        depth=full[column].shift(-1).to_numpy(float)
        valid &= np.isfinite(depth)&(depth>0)
    state=full.obi5_t0.shift(-1).to_numpy(float)
    valid &= np.isfinite(state)&(np.abs(state)<=1)
    continuation=np.zeros(n,bool)
    continuation[1:]=(valid[:-1]&valid[1:]&(hour[:-1]==hour[1:])&(episode[:-1]==episode[1:])
        &(ix[1:]==ix[:-1]+1)&(receipt[1:]>receipt[:-1])&(receipt[1:]-receipt[:-1]<=MAX_GAP_NS))
    segment=np.cumsum(valid&~continuation)-1
    segment[~valid]=-1
    return segment,valid,post_ok


def ranges(segment):
    starts=np.flatnonzero((segment>=0)&np.r_[True,segment[1:]!=segment[:-1]])
    for a in starts:
        b=a+1
        while b<len(segment) and segment[b]==segment[a]:b+=1
        yield a,b


def trailing_sum(x,w):
    c=np.r_[0.,np.cumsum(x)];i=np.arange(len(x))
    return c[i+1]-c[np.maximum(0,i-w+1)]


def build_features(full, segment):
    n=len(full);F=pd.DataFrame(np.nan,index=np.arange(n),columns=FEATURES)
    bd=full.bid_depth5_t0.shift(-1).to_numpy(float)
    ad=full.ask_depth5_t0.shift(-1).to_numpy(float)
    obi=full.obi5_t0.shift(-1).to_numpy(float)
    receipt=full.decision_receipt_ns.to_numpy(np.int64)
    mid=full.mid_t1.to_numpy(float)
    total=full.total_flow_qty.to_numpy(float);trades=full.n_trades.to_numpy(float)
    flow=full.signed_flow_qty.to_numpy(float)
    response=(full.bid_net_response-full.ask_net_response).to_numpy(float)
    for a,b in ranges(segment):
        size=b-a;i=np.arange(size);t=(receipt[a:b]-receipt[a])/1e6
        values={}
        values['obi_post']=obi[a:b]
        values['spread_bps']=full.spread_t1.to_numpy(float)[a:b]/mid[a:b]*10000
        values['bid_depth_percentile']=prior_percentile(bd[a:b])
        values['ask_depth_percentile']=prior_percentile(ad[a:b])
        # Current row is excluded from the typical-size denominator.
        tq=trailing_sum(total[a:b],200);tn=trailing_sum(trades[a:b],200)
        pq=np.r_[0.,tq[:-1]];pn=np.r_[0.,tn[:-1]]
        mean=np.divide(pq,pn,out=np.full(size,np.nan),where=pn>0)
        values['depth_in_prior_trades']=np.divide(bd[a:b]+ad[a:b],mean,out=np.full(size,np.nan),where=mean>0)
        values['dt_ms']=np.r_[np.nan,np.diff(t)]
        for name,arr in [('ntr',trades),('signed_flow',flow),('total_flow',total)]:values[name]=arr[a:b]
        for name,column in [('bid_add','bid_add_0_5_qty'),('bid_remove','bid_remove_0_5_qty'),
                            ('ask_add','ask_add_0_5_qty'),('ask_remove','ask_remove_0_5_qty')]:
            values[name]=full[column].to_numpy(float)[a:b]
        change=np.r_[np.nan,10000*np.diff(np.log(mid[a:b]))]
        movement=np.nan_to_num(change)
        values['mid_change_bps']=change
        last=np.maximum.accumulate(np.where(np.abs(movement)>1e-8,t,-np.inf))
        values['since_move_ms']=np.where(np.isfinite(last),t-last,np.nan)
        for w in (10,50,200):
            start=np.maximum(0,i-w);span=(t-t[start])/1000
            enough=(i>=w)&(span>0)
            values[f'book_rate_{w}']=np.divide(w,span,out=np.full(size,np.nan),where=enough)
            values[f'trade_rate_{w}']=np.divide(trailing_sum(trades[a:b],w),span,out=np.full(size,np.nan),where=enough)
        for w in (50,200):
            values[f'momentum_{w}_bps']=np.where(i>=w,trailing_sum(movement,w),np.nan)
            values[f'vol_{w}_bps']=np.where(i>=w,trailing_sum(np.abs(movement),w),np.nan)
        values['response_50_relative']=np.divide(trailing_sum(response[a:b],50),bd[a:b]+ad[a:b],out=np.full(size,np.nan),where=(i>=50)&((bd[a:b]+ad[a:b])>0))
        for seconds in (1,10,60):
            left=np.searchsorted(t,t-seconds*1000,side='right')
            enough=t>=seconds*1000
            for name,arr in [('flow',flow[a:b]),('trades',trades[a:b]),('vol',np.abs(movement))]:
                cumulative=np.r_[0.,np.cumsum(arr)]
                col=f'{name}_{seconds}s'+('_bps' if name=='vol' else '')
                values[col]=np.where(enough,cumulative[i+1]-cumulative[left],np.nan)
        for name,value in values.items():F.loc[a:b-1,name]=value
    return F.replace([np.inf,-np.inf],np.nan)


def build_targets(full, segment, horizon_ms):
    """Observed movement in (decision, deadline]; endpoint is last known state.

    A later receipt must confirm coverage through deadline within the same
    continuous segment. No rounding to whole ticks, no episode crossings.
    """
    n=len(full);receipt=full.decision_receipt_ns.to_numpy(np.int64);mid=full.mid_t1.to_numpy(float)
    target={k:np.full(n,np.nan) for k in ('any_move','endpoint_move','up','return_bps','endpoint_age_ms')}
    target['label_available_ns']=np.full(n,-1,dtype=np.int64)
    for a,b in ranges(segment):
        times=receipt[a:b];prices=mid[a:b];size=b-a;i=np.arange(size)
        deadline=times+horizon_ms*1_000_000
        endpoint=np.searchsorted(times,deadline,side='right')-1
        coverage=np.searchsorted(times,deadline,side='left')
        valid=(coverage<size)&(endpoint>=i)&(deadline-times[np.clip(endpoint,0,size-1)]<=MAX_GAP_NS)
        changed=np.r_[False,~np.isclose(prices[1:],prices[:-1],rtol=0,atol=1e-8)]
        cumulative=np.cumsum(changed)
        r=10000*np.log(prices[np.clip(endpoint,0,size-1)]/prices)
        # Count changes after the decision even if price returns to its anchor.
        any_move=(cumulative[np.clip(endpoint,0,size-1)]-cumulative[i])>0
        end_move=~np.isclose(prices[np.clip(endpoint,0,size-1)],prices,rtol=0,atol=1e-8)
        for name,value in [('any_move',any_move),('endpoint_move',end_move),('up',r>0),('return_bps',r),
                           ('label_available_ns',times[np.clip(coverage,0,size-1)]),
                           ('endpoint_age_ms',(deadline-times[np.clip(endpoint,0,size-1)])/1e6)]:
            target[name][a:b]=np.where(valid,value,-1 if name=='label_available_ns' else np.nan)
    return target


def lag_features(frame, segment, lags=CONTEXT):
    values={}
    for lag in range(lags):
        same=np.ones(len(frame),bool) if lag==0 else np.r_[np.zeros(lag,bool),segment[lag:]==segment[:-lag]]
        same &= segment>=0
        for name in frame:
            values[f'{name}_L{lag}']=frame[name].shift(lag).where(same).to_numpy(float)
    return pd.DataFrame(values)


class MatchedTokenizer:
    """Missing=0, exact zero=1, other values in training-fitted quantile bins."""
    def fit(self, frame, mask):
        self.edges={};self.centers={}
        for name in frame:
            x=frame.loc[mask,name].to_numpy(float);finite=x[np.isfinite(x)&(x!=0)]
            edges=np.unique(np.quantile(finite,np.linspace(0,1,BIN_COUNT+1)[1:-1])) if len(finite) else np.array([])
            if name.endswith('_percentile'):edges=np.linspace(0,1,BIN_COUNT+1)[1:-1]
            self.edges[name]=edges
            encoded=np.digitize(finite,edges)+2
            self.centers[name]={int(k):float(np.median(finite[encoded==k])) for k in np.unique(encoded)}
        return self
    def transform(self,frame):
        result={}
        for name in frame:
            x=frame[name].to_numpy(float)
            result[name]=np.where(~np.isfinite(x),0,np.where(x==0,1,np.digitize(x,self.edges[name])+2))
        return pd.DataFrame(result)
    def state(self):
        return dict(version=VERSION,bins=BIN_COUNT,edges={k:v.tolist() for k,v in self.edges.items()},centers=self.centers)


def classifier(categorical=False):
    return HistGradientBoostingClassifier(max_iter=150,learning_rate=.05,max_depth=4,
        min_samples_leaf=200,l2_regularization=1.,early_stopping=False,random_state=0,
        categorical_features='from_dtype' if categorical else None)


def scores(y,p,baseline):
    loss=float(log_loss(y,p,labels=[0,1]));base=float(log_loss(y,baseline,labels=[0,1]))
    return dict(n=len(y),positive_rate=float(np.mean(y)),log_loss=loss,baseline_log_loss=base,
        log_loss_skill=1-loss/base if base else None,brier=float(brier_score_loss(y,p)),
        auc=float(roc_auc_score(y,p)) if len(np.unique(y))>1 else None,
        accuracy_at_05=float(accuracy_score(y,p>=.5)))


def cost_scale(predictions,assumed_cost_bps=6.):
    """Oracle scale only: cannot stand in for a signal or executable backtest."""
    result=[]
    for horizon in HORIZONS_MS:
        frame=predictions[(predictions.horizon_ms==horizon)&(predictions.task=='endpoint_move')]
        changed=frame[frame.label==1]
        gross=float(frame.return_bps.abs().mean()) if len(frame) else None
        result.append(dict(horizon_ms=horizon,n=len(frame),n_endpoint_moves=len(changed),
            perfect_direction_mean_gross_bps=gross,
            perfect_direction_conditional_move_mean_gross_bps=float(changed.return_bps.abs().mean()) if len(changed) else None,
            assumed_round_trip_cost_bps=assumed_cost_bps,
            oracle_all_decisions_mean_after_cost_bps=gross-assumed_cost_bps if gross is not None else None,
            scope='Oracle scale diagnostic only, NOT strategy P/L or executable fills; 6 bp is an unverified cost scenario inherited from the supplied benchmark.'))
    return result


def main(repo,upload,out):
    started=time.monotonic();out=Path(out);out.mkdir(parents=True,exist_ok=True)
    hours,receipt_audit=load_receipt_hours(repo,upload)
    full=pd.concat(hours,ignore_index=True);names=[h.hour.iloc[0] for h in hours]
    segment,valid,post_ok=receipt_segments(full)
    F=build_features(full,segment);raw=lag_features(F,segment)
    pos=np.full(len(full),-1)
    for a,b in ranges(segment):pos[a:b]=np.arange(b-a)
    targets={h:build_targets(full,segment,h) for h in HORIZONS_MS}
    results=[];pooled={};predictions=[];token_audits=[];trial_count=0
    for fold in range(1,len(names)):
        train=full.hour.isin(names[:fold]).to_numpy();test=(full.hour==names[fold]).to_numpy()
        tokenizer=MatchedTokenizer().fit(F,train&valid)
        token=lag_features(tokenizer.transform(F),segment)
        # Match feature names and identical context; missing sentinels are declared.
        assert list(raw)==list(token)
        for column in token:
            token[column]=pd.Categorical(token[column],categories=np.arange(BIN_COUNT+2))
        (out/f'tokenizer_fold_{fold}.json').write_text(json.dumps(tokenizer.state(),indent=2))
        token_audits.append(dict(fold=fold,test_hour=names[fold],fit_rows=int((train&valid).sum()),
            training_hours=names[:fold],features=len(F.columns),matched_lagged_inputs=len(raw.columns)))
        for horizon,target in targets.items():
            eligible=valid&(pos>=WARMUP+CONTEXT)&np.isfinite(target['return_bps'])
            tr=eligible&train&(pos%3==0);te=eligible&test&(pos%10==0)
            for task in ('any_move','endpoint_move','up_given_endpoint_move'):
                label='up' if task.startswith('up_') else task
                trt=tr.copy();tet=te.copy()
                if label=='up':trt &= target['endpoint_move']==1;tet &= target['endpoint_move']==1
                y=target[label];ytr=y[trt].astype(int);yte=y[tet].astype(int)
                if len(ytr)<20 or len(yte)<2 or len(np.unique(ytr))<2:
                    results.append(dict(fold=fold,horizon_ms=horizon,task=task,model='skipped',n_train=len(ytr),n_test=len(yte),reason='insufficient training classes or evaluation rows'));continue
                # Never consume a training label extending into the test hour.
                assert np.all(target['label_available_ns'][trt]<full.loc[test,'decision_receipt_ns'].min())
                prior=np.full(len(yte),np.mean(ytr));model_preds={}
                for model_name,X in [('numeric',raw),('tokens',token)]:
                    model=classifier(model_name=='tokens');trial_count+=1
                    model.fit(X.loc[trt],ytr);p=model.predict_proba(X.loc[tet])[:,1]
                    result=dict(fold=fold,test_hour=names[fold],horizon_ms=horizon,task=task,model=model_name,
                        n_train=len(ytr),**scores(yte,p,prior))
                    results.append(result);pooled.setdefault((horizon,task,model_name),[]).append((yte,p,prior))
                    model_preds[model_name]=p
                indices=np.flatnonzero(tet)
                predictions.append(pd.DataFrame(dict(fold=fold,hour=names[fold],horizon_ms=horizon,task=task,
                    decision_ns=full.decision_receipt_ns.to_numpy()[indices],segment=segment[indices],label=yte,
                    label_available_ns=target['label_available_ns'][indices],return_bps=target['return_bps'][indices],
                    numeric_p=model_preds['numeric'],tokens_p=model_preds['tokens'],baseline_p=prior)))
        # Checkpoint after each completed fold, safe to resume/review if interrupted.
        (out/'FOLDS.json').write_text(json.dumps(results,indent=2,allow_nan=False))
        print(f'fold {fold}/4 complete: {names[fold]}',flush=True)
    pooled_scores=[]
    for (h,task,model),parts in pooled.items():
        y,p,prior=[np.concatenate([x[j] for x in parts]) for j in range(3)]
        pooled_scores.append(dict(horizon_ms=h,task=task,model=model,**scores(y,p,prior)))
    prediction=pd.concat(predictions,ignore_index=True)
    prediction.to_csv(out/'PREDICTIONS.csv.gz',index=False,compression='gzip')
    (out/'COST_SCALE.json').write_text(json.dumps(cost_scale(prediction),indent=2))
    target_audit=[]
    for h,t in targets.items():
        mask=np.isfinite(t['return_bps'])&valid&(pos>=WARMUP+CONTEXT)
        reversals=mask&(t['any_move']==1)&(t['endpoint_move']==0)
        target_audit.append(dict(horizon_ms=h,eligible_rows=int(mask.sum()),
            any_move_rate=float(np.mean(t['any_move'][mask])),endpoint_move_rate=float(np.mean(t['endpoint_move'][mask])),
            move_then_reversal_rows=int(reversals.sum()),max_endpoint_age_ms=float(np.max(t['endpoint_age_ms'][mask]))))
    summary=dict(version=VERSION,data_scope='Five previously examined non-contiguous Binance BTCUSDT recordings; development only.',
        status='WAIT',qualified=False,trial_count=trial_count,rows=len(full),valid_state_rows=int(valid.sum()),
        post_state_aligned_rows=int(post_ok.sum()),segments=int(segment.max()+1),policy=dict(
            clock='book receipt, processing latency 0 ms research diagnostic',max_event_receipt_age_ms=250,
            max_receipt_gap_ms=250,endpoint='as-of deadline, held last observed state; same-segment later coverage required',
            labels='any observed midpoint change and ending-price change are separate',
            normalization='strictly prior 256-observation percentile and prior 200-row mean trade size; reset each segment',
            train_stride=3,test_stride=10,overlap='Thinning is not independence; overlapping targets remain correlated.',
            feature_count=len(F.columns),lagged_input_count=len(raw.columns),token_bins=BIN_COUNT,
            summaries_seconds=[1,10,60],summary_warmup='Missing until uninterrupted window covered; no fabricated hourly summaries'),
        receipt_audit=receipt_audit,token_audit=token_audits,target_audit=target_audit,
        pooled=pooled_scores,folds=results,elapsed_seconds=time.monotonic()-started,
        limitations=['All periods were already examined; not untouched validation.',
            'AUC is ranking, not direction accuracy or profit.',
            'Only observed received-book movements; hidden moves between updates are unknown.',
            'Target coverage censoring excludes future feed gaps; scores do not cover every market condition.',
            'No fill, fee, slippage, inventory, maker queue or order execution qualification.',
            'Binance historical models cannot qualify the Kraken live venue.'])
    (out/'RESULTS.json').write_text(json.dumps(summary,indent=2,allow_nan=False))
    for row in pooled_scores:print(json.dumps(row),flush=True)
    print('saved',out,'elapsed',round(summary['elapsed_seconds'],1),'seconds',flush=True)
    return summary


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--repo',type=Path,default=Path('.'))
    parser.add_argument('--upload',type=Path,required=True)
    parser.add_argument('--out',type=Path,default=Path('docs/market_tokens/receipt_move_v3'))
    args=parser.parse_args();main(args.repo,args.upload,args.out)
