"""Prospective frozen-model diagnostics with hypothetical top-quote outcomes."""
import copy,hashlib,json,math
from collections import deque
import numpy as np
from .paper_signal import assess

class PaperLedger:
    def __init__(self):
        self.model=None;self.frozen_ns=None;self.model_id=None;self.pending=None;self.last_decision=-10**18
        self.rows=deque(maxlen=20);self.resolved=0;self.invalid=0;self.trades=0;self.net_sum=0.;self.loss_sum=0.;self.zero_loss_sum=0.;self.complete=False
    def update(self,report,view,now):
        if self.model is None and report.get('return_model'):
            self.model=copy.deepcopy(report);self.frozen_ns=now
            self.model_id=hashlib.sha256(json.dumps(self.model,sort_keys=True).encode()).hexdigest()[:16]
        mo=view.get('model_observation');valid=bool(mo and view.get('research_usable') and view.get('bids') and view.get('asks'))
        if valid:
            valid=(self.model is not None and (mo['provider'],mo['symbol'])==(self.model.get('venue'),self.model.get('symbol')) and 0<=now-mo['available_ns']<=250_000_000 and 0<=mo['available_ns']-mo['event_ns']<=250_000_000)
        if self.pending:
            p=self.pending
            if not valid or now>p['decision_ns']+1_250_000_000:
                self.invalid+=1;self.pending=None
            elif now>=p['decision_ns']+1_000_000_000 and mo['available_ns']>=p['decision_ns']+1_000_000_000:
                bid=float(view['bids'][0][0]);ask=float(view['asks'][0][0]);mid=(bid+ask)/2
                target=10000*math.log(mid/p['mid']);self.loss_sum+=(p['expected']-target)**2;self.zero_loss_sum+=target**2;self.resolved+=1
                net=None
                if p['signal'] in ('BUY','SELL'):
                    gross=10000*(bid/p['ask']-1) if p['signal']=='BUY' else 10000*(p['bid']-ask)/p['bid']
                    net=gross-6;self.trades+=1;self.net_sum+=net
                self.rows.append(dict(decision_ns=p['decision_ns'],resolved_ns=now,signal=p['signal'],expected_bps=p['expected'],midpoint_return_bps=target,quote_proxy_net_bps=net));self.pending=None
        if self.model and now-self.frozen_ns>=600_000_000_000:self.complete=True
        if valid and not self.complete and self.pending is None and now-self.last_decision>=1_250_000_000:
            bid=float(view['bids'][0][0]);ask=float(view['asks'][0][0]);x=mo['features'];m=self.model['return_model']
            if 0<bid<ask and len(x)==5 and all(math.isfinite(v) for v in x):
                expected=float(np.r_[1,(np.array(x)-m['center'])/m['scale']]@m['weights']);signal=assess(self.model,view,now)['signal']
                self.pending=dict(decision_ns=now,mid=(bid+ask)/2,bid=bid,ask=ask,expected=expected,signal=signal);self.last_decision=now
        return dict(status='complete' if self.complete else 'frozen_evaluation' if self.model else 'waiting_for_fit',frozen_model_id=self.model_id,frozen_ns=self.frozen_ns,resolved_forecasts=self.resolved,invalidated_forecasts=self.invalid,pending=self.pending is not None,forecast_mse=self.loss_sum/self.resolved if self.resolved else None,zero_return_mse=self.zero_loss_sum/self.resolved if self.resolved else None,paper_trades=self.trades,quote_proxy_net_sum_bps=self.net_sum,latest=list(self.rows),orders_enabled=False,qualified=False,caveat='One frozen ten-minute evaluation; hypothetical immediate top-quote fills, 6 bps fee/slippage assumptions; no actual execution, inventory or profitability qualification. Resets on restart.')
