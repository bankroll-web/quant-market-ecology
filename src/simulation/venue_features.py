"""Receipt-bundle features for bounded validated spot books."""
from decimal import Decimal
import math


def observation(observer,before,received_ns):
    if before is None or observer.event_ms is None:return None
    bid,ask=max(observer.bids),min(observer.asks);qb,qa=observer.bids[bid],observer.asks[ask]
    old_bid,old_qb,old_ask,old_qa=before
    ofi=(qb if bid>=old_bid else 0)-(old_qb if bid<=old_bid else 0)-(qa if ask<=old_ask else 0)+(old_qa if ask>=old_ask else 0)
    mid=(bid+ask)/2;db=sum(q for p,q in observer.bids.items() if p>=mid*Decimal('.999'));da=sum(q for p,q in observer.asks.items() if p<=mid*Decimal('1.001'));depth=db+da
    if depth<=0:return None
    return dict(provider=observer.provider,symbol=observer.symbol,source_update_id=observer.sequence,event_ns=observer.event_ms*1000000,available_ns=received_ns,
        features=[float((qb-qa)/(qb+qa)),float((db-da)/depth),math.log(float(depth)),float((ask-bid)/mid*10000),float(ofi/depth)],
        midpoint=float(mid),best_quote_ofi_btc=float(ofi),depth_btc=float(depth),feature_scope='Subscribed validated Kraken depth; venue-specific model required')
