"""Receipt-causal Coinbase token learning. Research forecasts, never orders.

Fixed bins are a new live policy, not the Binance historical tokenizer.
Only verified matches and validated book observations enter this learner.
"""
from collections import deque, Counter
import bisect
import json
import math
from pathlib import Path
import uuid

FIELDS = ('dt_ms','trade_count','signed_flow_btc','bid_added_btc','bid_removed_btc',
          'ask_added_btc','ask_removed_btc','mid_delta_bps','top_obi',
          'depth_imbalance','depth_btc','spread_bps')
EDGES = ([10,25,50,100,250,500,1000], [0,1,2,4,8,16,32],
         [-1,-.1,-.01,0,.01,.1,1], *([0,.001,.01,.1,1,10,100],)*4,
         [-2,-.5,-.1,0,.1,.5,2], *([-.75,-.5,-.25,0,.25,.5,.75],)*2,
         [.1,1,5,10,25,50,100], [.01,.05,.1,.25,.5,1,2])
VERSION = 'coinbase-receipt-fixed-bins-v2'
HORIZON_NS = 30_000_000_000


class RiverLive:
    def __init__(self, checkpoint=None, provider='Coinbase Exchange', symbol='BTC-USD', seed_checkpoint=None):
        from river import linear_model, optim
        self.model = linear_model.LinearRegression(optimizer=optim.SGD(.005),
            l2=.0001, clip_gradient=10)
        self.checkpoint = Path(checkpoint) if checkpoint else None
        self.provider,self.symbol=provider,symbol
        self.version=VERSION if provider=='Coinbase Exchange' else 'kraken-receipt-fixed-bins-v2'
        self.session = uuid.uuid4().hex[:12]
        self.context = deque(maxlen=16)
        self.pending = deque()
        self.recent = deque(maxlen=100)
        self.last_ns = self.last_mid = None
        self.last_decision_ns = 0
        self.trade_count = 0
        self.flow = 0.
        self.events = self.updates = self.decisions = self.dropped = 0
        self.loss = self.zero_loss = self.mean_loss = self.target_sum = 0.
        self.patterns = {}
        self.status = 'waiting for validated Coinbase observations'
        self.restored = False
        self.last_save_ns = 0
        self.latest = None
        source = self.checkpoint if self.checkpoint and self.checkpoint.exists() else (Path(seed_checkpoint) if seed_checkpoint else None)
        self.restore_source = None
        self.journal = None
        if self.checkpoint:
            from .capture_archive import CaptureArchive
            self.journal = CaptureArchive(self.checkpoint.parent / (self.checkpoint.stem + "-journal"))
        if source and source.exists():
            try:
                data = json.loads(source.read_text())
                if data['version'] != self.version or data['river_version'] != '0.26.1':
                    raise ValueError('checkpoint version mismatch')
                weights = data['weights']
                if len(weights)>2000 or any(not math.isfinite(float(v)) for v in weights.values()):
                    raise ValueError('invalid weights')
                for key,value in weights.items():
                    self.model._weights[key] = float(value)
                self.model.intercept = float(data['intercept'])
                if not math.isfinite(self.model.intercept):raise ValueError('invalid intercept')
                for key in ('events','updates','decisions','dropped','loss','zero_loss','mean_loss','target_sum'):
                    value=data[key]
                    if not math.isfinite(value) or (key!='target_sum' and value<0):raise ValueError('invalid counters')
                    setattr(self,key,value)
                self.patterns=data['patterns']
                self.restored=True
                self.restore_source = "local" if source == self.checkpoint else "saved_seed"
            except (KeyError,TypeError,ValueError,OSError):
                # Malformed checkpoints fail closed instead of loading partial weights.
                self.model = linear_model.LinearRegression(optimizer=optim.SGD(.005),l2=.0001,clip_gradient=10)
                self.events = self.updates = self.decisions = self.dropped = 0
                self.loss = self.zero_loss = self.mean_loss = self.target_sum = 0.
                self.patterns={}

    def reset(self, reason):
        self.dropped += len(self.pending)
        self.pending.clear()
        self.context.clear()
        self.last_ns = self.last_mid = None
        self.trade_count = 0
        self.flow = 0.
        self.latest = None
        self.status = reason

    def record(self, kind, payload, received_ns):
        if kind.endswith('disconnect'):
            self.reset('paused: feed disconnected; pending labels discarded')
            return
        if kind in ('coinbase_verified_match','kraken_verified_match'):
            if self.last_ns is not None and received_ns > self.last_ns:
                self.trade_count += 1
                self.flow += float(payload['qty']) * (1 if payload['side']=='buy' else -1)
            return
        if kind not in ('coinbase_model_observation','kraken_model_observation'):return
        self.observe(payload, received_ns)

    def observe(self, obs, received_ns):
        if not obs.get('trade_subscription_active'):
            self.reset('paused: trade subscription unavailable');return
        if obs.get('provider')!=self.provider or obs.get('symbol')!=self.symbol:
            self.reset('paused: venue mismatch');return
        event_ns=obs.get('event_ns')
        if not isinstance(event_ns,int) or not 0<=received_ns-event_ns<=2_000_000_000:
            self.reset('paused: invalid clock or more than 2 seconds of feed delay');return
        if received_ns-event_ns>250_000_000:
            # A delayed intermediate row is not an input or a target. Return
            # labels need valid endpoints, not every intermediate book state.
            # Preserve pending endpoints until a real continuity gap occurs.
            self.context.clear();self.latest=None
            self.status='paused: intermediate row outside 250 ms cutoff; rebuilding context'
            return
        if self.last_ns is not None and (received_ns<=self.last_ns or received_ns-self.last_ns>2_000_000_000):
            self.reset('paused: book receipt gap or reversed timestamp')
        try:
            mid=float(obs['midpoint']); f=list(map(float,obs['features']))
            changes=obs.get('liquidity_changes',{})
            vals=[0 if self.last_ns is None else (received_ns-self.last_ns)/1e6,
                  self.trade_count,self.flow,
                  *[float(changes.get(k,0)) for k in FIELDS[3:7]],
                  0 if self.last_mid is None else (mid/self.last_mid-1)*10000,
                  f[0],f[1],float(obs['depth_btc']),f[3]]
            if mid<=0 or len(f)!=5 or any(not math.isfinite(v) for v in vals):raise ValueError('invalid features')
        except (KeyError,IndexError,ValueError,TypeError):
            self.reset('paused: invalid observation');return
        # Outcomes only exist after the first valid receipt at/after the deadline.
        while self.pending and self.pending[0]['due_ns']<=received_ns:
            p=self.pending.popleft()
            if received_ns-p['due_ns']>2_000_000_000:
                self.dropped+=1;continue
            actual=(mid/p['mid']-1)*10000
            self.loss+=(p['forecast_bps']-actual)**2
            self.zero_loss+=actual**2
            self.mean_loss+=(p['baseline_bps']-actual)**2
            self.updates+=1
            self.target_sum+=actual
            row={k:v for k,v in p.items() if k not in ('x','mid','due_ns')}
            row.update(actual_bps=actual,outcome_ns=received_ns)
            self.recent.append(row)
            if self.journal:
                self.journal.append("river_outcome", dict(session=self.session, version=self.version, **row), received_ns)
            pattern=self.patterns.setdefault(p['pattern'],dict(count=0,sum_bps=0.,sum_sq_bps=0.))
            pattern['count']+=1;pattern['sum_bps']+=actual;pattern['sum_sq_bps']+=actual**2
            # Scored pre-update prediction above; then, and only then, learn.
            self.model.learn_one(p['x'],actual)
        tokens=[bisect.bisect_right(edges,v) for edges,v in zip(EDGES,vals)]
        self.context.append(tokens);self.events+=1
        self.last_ns=received_ns;self.last_mid=mid;self.trade_count=0;self.flow=0.
        self.latest=dict(received_ns=received_ns,values=dict(zip(FIELDS,vals)),tokens=dict(zip(FIELDS,tokens)))
        if len(self.context)==16 and received_ns-self.last_decision_ns>=1_000_000_000:
            x={f'last:{i}:{token}':1/12 for i,token in enumerate(tokens)}
            counts=Counter((i,t) for row in self.context for i,t in enumerate(row))
            x.update({f'context:{i}:{token}':n/(16*12) for (i,token),n in counts.items()})
            prediction=float(self.model.predict_one(x))
            if not math.isfinite(prediction):self.reset('paused: nonfinite prediction');return
            # Predeclared guard against unstable research output, not a learned bin.
            prediction=max(-100.,min(100.,prediction))
            direction='buy flow' if vals[2]>.01 else 'sell flow' if vals[2]<-.01 else 'balanced flow'
            liquidity='ask net reduction > bid' if vals[6]-vals[5]>vals[4]-vals[3] else 'bid net reduction >= ask'
            self.pending.append(dict(x=x,mid=mid,decision_ns=received_ns,
                due_ns=received_ns+HORIZON_NS,forecast_bps=prediction,
                baseline_bps=self.target_sum/self.updates if self.updates else 0.,
                pattern=f'{direction} / {liquidity}'))
            if self.journal:
                saved={k:v for k,v in self.pending[-1].items() if k not in ("x","mid")}
                self.journal.append("river_decision", dict(session=self.session,version=self.version,token_values=vals,tokens=tokens,**saved),received_ns)
            self.decisions+=1;self.last_decision_ns=received_ns
        self.status='learning after delayed outcomes' if self.updates else 'warming up: waiting for 30-second outcomes'

    def snapshot(self):
        return dict(version=self.version,river_version='0.26.1',weights=self.model.weights,
            intercept=self.model.intercept,patterns=self.patterns,
            **{k:getattr(self,k) for k in ('events','updates','decisions','dropped','loss','zero_loss','mean_loss','target_sum')})

    def view(self, now_ns, market, usable, trades_active):
        if market.get('provider')!=self.provider or market.get('symbol')!=self.symbol or not usable or not trades_active:
            self.reset('paused: matching validated book and trade subscription required')
        if self.last_ns is not None and now_ns-self.last_ns>2_000_000_000:
            self.reset('paused: no fresh receipt for 2 seconds')
        if self.checkpoint and now_ns-self.last_save_ns>=10_000_000_000:
            self.checkpoint.parent.mkdir(parents=True,exist_ok=True)
            tmp=self.checkpoint.with_suffix('.tmp');tmp.write_text(json.dumps(self.snapshot(),allow_nan=False));tmp.replace(self.checkpoint)
            self.last_save_ns=now_ns
        return dict(generated_ns=now_ns,version=self.version,session=self.session,status=self.status,
            venue=self.provider+' '+self.symbol,horizon_seconds=30,continuous_learning=True,
            qualified=False,signal='WAIT',restored=self.restored,restore_source=self.restore_source,
            learning_journal=self.journal.view() if self.journal else None,
            persistence='Local checkpoint and forecast/outcome journal are ephemeral. Saved seed restores only its backup point after storage loss; download newer backups.',
            events=self.events,tokens=self.events*12,decisions=self.decisions,learned_outcomes=self.updates,
            pending=len(self.pending),discarded_labels=self.dropped,
            mse_bps2=self.loss/self.updates if self.updates else None,
            zero_baseline_mse_bps2=self.zero_loss/self.updates if self.updates else None,
            prior_mean_baseline_mse_bps2=self.mean_loss/self.updates if self.updates else None,
            skill_vs_zero=1-self.loss/self.zero_loss if self.zero_loss else None,
            latest=self.latest,recent=list(self.recent),patterns=self.patterns,
            forecast={k:v for k,v in self.pending[-1].items() if k not in ('x','mid')} if self.pending else None,
            limitations=['Adaptive prequential evaluation, not an untouched holdout.',
                'Overlapping 30-second outcomes are correlated; counts are not independent trials.',
                'No fees, execution or profit qualification; anonymous flow does not identify participants.'])
