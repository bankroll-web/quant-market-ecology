"""Exploratory paper candidates. Never authorizes actual orders."""
import math
import numpy as np

def fit_return(x,y,xe,ye):
    center=x.mean(0);scale=x.std(0);scale=np.where(scale>0,scale,1)
    z=np.column_stack([np.ones(len(x)),(x-center)/scale]);pen=np.eye(z.shape[1]);pen[0,0]=0
    w=np.linalg.solve(z.T@z+.1*len(x)*pen,z.T@y)
    p=np.column_stack([np.ones(len(xe)),(xe-center)/scale])@w
    lower=x.min(0);upper=x.max(0);supported=((xe>=lower)&(xe<=upper)).all(1)
    positions=np.where(p>8,1,np.where(p<-8,-1,0));positions[~supported]=0;net=positions*ye-np.abs(positions)*6
    return dict(center=center.tolist(),scale=scale.tolist(),weights=w.tolist(),feature_lower=lower.tolist(),feature_upper=upper.tolist(),supported_evaluation=int(supported.sum()),mse=float(np.mean((p-ye)**2)),zero_mse=float(np.mean(ye**2)),evaluation_candidates=int(np.count_nonzero(positions)),evaluation_net_mean_bps=float(net[positions!=0].mean()) if np.any(positions) else None,assumed_roundtrip_cost_bps=6,buffer_bps=2)

def assess(report,view,now_ns):
    result=dict(signal='WAIT',mode='paper_research_only',qualified=False,orders_enabled=False,reasons=[],expected_move_bps=None,horizon_seconds=1)
    reasons=result['reasons'];mo=view.get('model_observation');m=report.get('return_model')
    if not view.get('research_usable'):reasons.append('Feed is not research-fresh')
    if m is None:reasons.append('Expected-return model is not fitted')
    if not mo:reasons.append('Live features unavailable')
    if mo:
        if (report.get('venue'),report.get('symbol'))!=(mo.get('provider'),mo.get('symbol')):reasons.append('Model and feed venues differ')
        age=now_ns-mo.get('available_ns',0);engine_age=mo.get('available_ns',0)-mo.get('event_ns',0)
        if not 0<=age<=250_000_000 or not 0<=engine_age<=250_000_000:reasons.append('Feature bundle delayed or clock invalid')
        if mo.get('available_ns',now_ns+1)>now_ns:reasons.append('Feature availability is in the future')
    if not 0<=now_ns-report.get('last_label_ns',0)<=600_000_000_000:reasons.append('Model data is absent or older than ten minutes')
    if m:
        if mo:
            x=mo.get('features',[])
            if len(x)!=5 or not all(math.isfinite(v) for v in x):reasons.append('Invalid features')
            elif 'feature_lower' not in m or 'feature_upper' not in m:reasons.append('Training feature support unavailable')
            elif any(v<lo or v>hi for v,lo,hi in zip(x,m['feature_lower'],m['feature_upper'])):reasons.append('Live features outside training support; extrapolation rejected')
        if not m['mse']<m['zero_mse']:reasons.append('Development forecast does not beat zero-return baseline')
        if m['evaluation_candidates']<20 or (m['evaluation_net_mean_bps'] or 0)<=0:reasons.append('Insufficient positive cost-adjusted development candidates')
    if not reasons:
        x=mo['features']
        if len(x)!=5 or not all(math.isfinite(v) for v in x):reasons.append('Invalid features')
        else:
            estimate=float(np.r_[1,(np.array(x)-m['center'])/m['scale']]@m['weights']);result['expected_move_bps']=estimate
            threshold=m['assumed_roundtrip_cost_bps']+m['buffer_bps']
            result['signal']='BUY' if estimate>threshold else 'SELL' if estimate<-threshold else 'WAIT'
            if result['signal']=='WAIT':reasons.append('Estimated movement does not exceed assumed costs plus buffer')
    reasons.append('Exploratory paper candidate; no untouched-period or executable-fill qualification')
    return result
