"""Live model integration status. Unqualified models must abstain."""
import math
from .frozen_probability_model import ARTIFACT


def assess(market,view,decision_ns):
    reasons=[]
    if not view.get('research_usable'):reasons.append('Feed unavailable, delayed or not research quality')
    if market.get('provider')!='Binance Futures' or market.get('symbol')!='BTCUSDT':reasons.append('Training venue is Binance Futures BTCUSDT; this live venue has not been validated')
    observation=view.get('model_observation');probability=None
    if not observation:reasons.append('Exact training-compatible receipt-bundle features are unavailable')
    else:
        values=observation.get('features',[]);available=observation.get('available_ns')
        if type(available) is not int or available>decision_ns or decision_ns-available>250_000_000:reasons.append('Model features are stale or unavailable at decision time')
        elif len(values)!=len(ARTIFACT['features']) or not all(isinstance(v,(float,int)) and math.isfinite(v) for v in values):reasons.append('Invalid model features')
        elif not reasons:
            m=ARTIFACT['model'];z=m['weights'][0]+sum(w*(x-c)/s for w,x,c,s in zip(m['weights'][1:],values,m['center'],m['scale']))
            probability=1/(1+math.exp(-max(-40,min(40,z))))
    reasons.append('Model is exploratory; no cost-aware profitable policy or live qualification exists')
    return dict(signal='WAIT',mode='read_only_shadow',model_loaded=True,model_id=ARTIFACT['model_id'],
        trained_on=ARTIFACT['trained_on'],features=ARTIFACT['features'],positive_return_probability=probability,
        target='Approximately one-second positive midpoint return; zero is nonpositive',reasons=reasons,
        orders_enabled=False,online_training_enabled=False)
