"""Rolling observed liquidity/flow mechanics; no identity or causal inference."""
from collections import deque
import math

KEYS=('bid_added_btc','bid_removed_btc','ask_added_btc','ask_removed_btc',
      'taker_buy_btc','taker_sell_btc')

class MarketMechanics:
    def __init__(self,window_seconds=10,max_events=50000):
        self.window_ns=int(window_seconds*1e9)
        self.max_events=max_events
        self.reset()

    def reset(self):
        self.events=deque();self.totals={k:0. for k in KEYS}
        self.started_ns=None;self.last_ns=None;self.capacity_lost_until_ns=0
        self.seen_ids=set();self.id_queue=deque();self.excluded_trades=deque()

    def trim(self,now_ns):
        cutoff=now_ns-self.window_ns
        while self.events and self.events[0][0]<cutoff:
            _,values,_=self.events.popleft()
            for key,value in values.items():self.totals[key]-=value
        while self.excluded_trades and self.excluded_trades[0]<cutoff:self.excluded_trades.popleft()

    def record(self,received_ns,values=None,midpoint=None):
        values=values or {}
        if any(k not in KEYS or not math.isfinite(v) or v<0 for k,v in values.items()):
            raise ValueError('Invalid observed quantity')
        if self.last_ns is not None and received_ns<self.last_ns:self.reset()
        if self.started_ns is None:self.started_ns=received_ns
        self.last_ns=received_ns;self.trim(received_ns)
        self.events.append((received_ns,dict(values),midpoint))
        for key,value in values.items():self.totals[key]+=value
        if len(self.events)>self.max_events:
            ts,old,_=self.events.popleft()
            for key,value in old.items():self.totals[key]-=value
            self.capacity_lost_until_ns=max(self.capacity_lost_until_ns,ts+self.window_ns)

    def trade(self,trade,received_ns):
        # IDs deduplicate metrics only; raw capture retains every received message.
        try:
            tid=int(trade['trade_id']);qty=float(trade['qty']);side=trade['side']
            if tid<0 or not math.isfinite(qty) or qty<=0 or side not in ('buy','sell'):raise ValueError()
        except (KeyError,ValueError,TypeError):
            self.excluded_trades.append(received_ns);return False
        if tid in self.seen_ids:return False
        self.seen_ids.add(tid);self.id_queue.append(tid)
        if len(self.id_queue)>self.max_events:self.seen_ids.remove(self.id_queue.popleft())
        self.record(received_ns,{('taker_buy_btc' if side=='buy' else 'taker_sell_btc'):qty})
        return True

    def view(self,now_ns,book_usable,trade_subscribed):
        self.trim(now_ns)
        coverage=0. if self.started_ns is None else min(self.window_ns,max(0,now_ns-self.started_ns))/1e9
        complete=(book_usable and trade_subscribed and coverage>=self.window_ns/1e9
                  and now_ns>self.capacity_lost_until_ns and not self.excluded_trades)
        if not book_usable or not trade_subscribed:
            return dict(status='unavailable',coverage_seconds=coverage,window_seconds=self.window_ns/1e9)
        qty={k:max(0.,v) for k,v in self.totals.items()}
        total=qty['taker_buy_btc']+qty['taker_sell_btc']
        mids=[mid for _,_,mid in self.events if mid is not None]
        return dict(status='observed' if complete else 'warming_or_incomplete',window_seconds=self.window_ns/1e9,
                    coverage_seconds=coverage,**qty,
                    signed_taker_btc=qty['taker_buy_btc']-qty['taker_sell_btc'],
                    taker_imbalance=(qty['taker_buy_btc']-qty['taker_sell_btc'])/total if total else None,
                    bid_add_remove_ratio=qty['bid_added_btc']/qty['bid_removed_btc'] if qty['bid_removed_btc'] else None,
                    ask_add_remove_ratio=qty['ask_added_btc']/qty['ask_removed_btc'] if qty['ask_removed_btc'] else None,
                    observed_midpoint_move_bps=(mids[-1]/mids[0]-1)*10000 if len(mids)>1 else None,
                    excluded_trade_events=len(self.excluded_trades),
                    interpretation='Receipt-window associations. L2 reductions combine executions, cancellations and other changes; no participant identity or causal attribution.')
