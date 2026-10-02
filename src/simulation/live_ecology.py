"""Counterfactual experiments on a frozen live L2 book; no participant inference."""
from collections import deque
from decimal import Decimal
import math
import random
import statistics


def walk(bids, asks, signed_btc):
    """Consume absolute displayed quantities; preserve caller's book."""
    if not math.isfinite(signed_btc):
        raise ValueError('order size must be finite')
    bids, asks = dict(bids), dict(asks)
    remaining = Decimal(str(abs(signed_btc)))
    requested = remaining
    notional = Decimal(0)
    side = asks if signed_btc >= 0 else bids
    for price in sorted(side, reverse=signed_btc < 0):
        taken = min(side[price], remaining)
        notional += taken * price
        remaining -= taken
        side[price] -= taken
        if side[price] == 0:
            del side[price]
        if remaining == 0:
            break
    filled = requested - remaining
    mid = (max(bids) + min(asks)) / 2 if bids and asks else None
    return dict(requested_btc=float(requested), filled_btc=float(filled),
                unfilled_btc=float(remaining), vwap=float(notional/filled) if filled else None,
                midpoint=float(mid) if mid is not None else None,
                bids=bids, asks=asks)


def experiment(bids, asks, signed_btc, liquidity_fraction=1., gamma=0.):
    """One immediate order and one hedge round; gamma in BTC per USDT."""
    if not 0 < liquidity_fraction <= 1 or not math.isfinite(gamma):
        raise ValueError('invalid scenario parameter')
    before = float((max(bids)+min(asks))/2)
    fraction = Decimal(str(liquidity_fraction))
    first = walk({p:q*fraction for p,q in bids.items()},
                 {p:q*fraction for p,q in asks.items()}, signed_btc)
    # dH = -Gamma * dS. Position sign is an assumption, never derived from OI.
    hedge = -gamma*(first['midpoint']-before) if first['midpoint'] is not None else 0.
    second = walk(first['bids'], first['asks'], hedge) if hedge else first
    after = second['midpoint']
    return dict(order_btc=signed_btc, liquidity_fraction=liquidity_fraction,
                assumed_gamma_btc_per_usdt=gamma, initiating_filled_btc=first['filled_btc'],
                initiating_unfilled_btc=first['unfilled_btc'], initiating_vwap=first['vwap'],
                hedge_signed_btc=hedge, hedge_filled_btc=second['filled_btc'] if hedge else 0.,
                hedge_unfilled_btc=second['unfilled_btc'] if hedge else 0.,
                midpoint_before=before, midpoint_after=after,
                move_usdt=after-before if after is not None else None,
                move_bps=(after/before-1)*10000 if after is not None else None,
                book_exhausted=after is None)


def black_scholes(spot, strike, years, volatility, rate=0.):
    """European cash price and spot delta/gamma; explicit caller inputs only."""
    if not all(math.isfinite(x) for x in (spot,strike,years,volatility,rate)):
        raise ValueError('inputs must be finite')
    if min(spot,strike,years,volatility) <= 0:
        raise ValueError('positive spot, strike, expiry and volatility required')
    d1=(math.log(spot/strike)+(rate+volatility**2/2)*years)/(volatility*math.sqrt(years))
    d2=d1-volatility*math.sqrt(years)
    cdf=lambda x: (1+math.erf(x/math.sqrt(2)))/2
    call=spot*cdf(d1)-strike*math.exp(-rate*years)*cdf(d2)
    put=call-spot+strike*math.exp(-rate*years)
    gamma=math.exp(-d1*d1/2)/math.sqrt(2*math.pi)/(spot*volatility*math.sqrt(years))
    return dict(call=call,put=put,call_delta=cdf(d1),put_delta=cdf(d1)-1,gamma=gamma)


class LiveEcology:
    def __init__(self):
        self.samples=deque(maxlen=301)
        self.last_bucket=None
        self.last_sequence=None
        self.history=deque(maxlen=120)
        self.previous=None
        self.rollouts=None

    def update(self, observer, now_ns):
        view=observer.view(now_ns)
        bucket=now_ns//1_000_000_000
        if not view['usable']:
            self.samples.clear()
            self.last_bucket=None
            self.last_sequence=None
            self.previous=None
            self.rollouts=None
            return dict(status='paused',reason=view['status'],scenarios=[],monte_carlo=None,
                        history=list(self.history),models=self.models())
        if bucket == self.last_bucket:
            return self.previous
        if self.last_bucket is not None and bucket-self.last_bucket != 1:
            self.samples.clear()  # Do not estimate variance across unavailable time.
        self.last_bucket=bucket
        self.last_sequence=view['last_update_id']
        self.samples.append((bucket,view['mid']))
        scenarios=[]
        specs=[('Small simulated buyer',.1,1.,0.),
               ('Large simulated buyer',10.,1.,0.),('Large simulated seller',-10.,1.,0.),
               ('Buy after 50% liquidity withdrawal',10.,.5,0.),
               ('Buy + assumed long-gamma hedge',10.,1.,.05),
               ('Buy + assumed short-gamma hedge',10.,1.,-.05)]
        for name, size, fraction, gamma in specs:
            scenarios.append(dict(name=name,**experiment(observer.bids,observer.asks,size,fraction,gamma)))
        self.history.append(dict(time_ms=now_ns//1_000_000,observed_mid=view['mid'],
                                 large_buy_mid=scenarios[1]['midpoint_after'],
                                 thin_buy_mid=scenarios[3]['midpoint_after']))
        if self.rollouts is None or bucket % 10 == 0:
            from .live_rollout import rollout
            self.rollouts = dict(generated_ns=now_ns,source_update_id=view['last_update_id'],
                baseline=rollout(observer.bids,observer.asks),
                withdrawal=rollout(observer.bids,observer.asks,withdrawal=True),
                short_gamma=rollout(observer.bids,observer.asks,signed_gamma=-.05))
        self.previous=dict(rollouts=self.rollouts,status='running',reason=view['status'],research_usable=view['research_usable'],receipt_minus_event_ms=view['receipt_minus_event_ms'],silence_ms=view['silence_ms'],source_update_id=self.last_sequence,
                           observed_mid=view['mid'],scenarios=scenarios,monte_carlo=self.monte_carlo(),
                           history=list(self.history),models=self.models())
        return self.previous

    def monte_carlo(self):
        if len(self.samples)<61:
            return dict(status='warming_up',samples=len(self.samples),required=61)
        returns=[math.log(b[1]/a[1]) for a,b in zip(self.samples,list(self.samples)[1:])]
        variance=statistics.variance(returns)
        sigma=math.sqrt(variance)  # log-return standard deviation per sqrt(second).
        horizon=60
        rng=random.Random(731)
        spot=self.samples[-1][1]
        # Zero expected price drift under GBM. No fitted directional/alpha claim.
        terminal=[]
        for _ in range(500):
            z=rng.gauss(0,1)
            for sign in (-1,1):
                terminal.append(spot*math.exp(-variance*horizon/2+sigma*math.sqrt(horizon)*sign*z))
        terminal.sort()
        return dict(status='illustrative',model='zero-drift GBM Monte Carlo',paths=1000,seed=731,
                    horizon_seconds=horizon,return_samples=len(returns),
                    sigma_per_sqrt_second=sigma,p05=terminal[49],p50=(terminal[499]+terminal[500])/2,
                    p95=terminal[949],expected_price=spot,
                    caveat='Rolling variance only; unvalidated scenario interval, not a forecast confidence interval.')

    @staticmethod
    def models():
        return dict(book_walk='Active: frozen displayed L2, immediate execution, no replenishment or queue fills.',
                    participants='Scenario roles only. Anonymous L2 cannot identify retail, institutions or dealers.',
                    gamma='Assumed signed gamma ±0.05 BTC/USDT, one hedge round; measured GEX unavailable.',
                    options='Black-Scholes utility available offline with explicit inputs; option chain/surface/positions absent.',
                    learning='Existing synthetic tabular policy remains unpromoted; no live training or policy orders.',
                    hawkes='Existing stationary synthetic Hawkes environment remains separate; depth deletions are not trade prints.',
                    macro_auction='Macro bubble and venue auction branches remain separate.')
