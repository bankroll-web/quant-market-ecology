"""Optional bounded Postgres checkpoints. Never store credentials in reports."""
import copy,json,math,os,time
from concurrent.futures import ThreadPoolExecutor

KEY='market-ecology-live-observer'

def snapshot(training,ledger):
    state=dict(schema=1,saved_ns=time.time_ns(),training=dict(venue=list(training.venue) if training.venue else None,examples=copy.deepcopy(training.examples),report=copy.deepcopy(training.report)),ledger={k:copy.deepcopy(getattr(ledger,k)) for k in ('model','frozen_ns','model_id','resolved','invalid','trades','net_sum','loss_sum','zero_loss_sum','complete')})
    state['ledger']['latest']=list(ledger.rows);state['ledger']['invalid']+=int(ledger.pending is not None)
    json.dumps(state,allow_nan=False)
    return state

def restore(state,training,ledger):
    if state.get('schema')!=1:raise ValueError('Unsupported checkpoint schema')
    t=state['training'];venue=tuple(t['venue']) if t['venue'] else None;examples=t['examples']
    if len(examples)>20000:raise ValueError('Oversized checkpoint')
    previous=-1
    for row in examples:
        if row['decision_ns']<=previous or row['label_available_ns']<row['target_end_ns'] or row['target_end_ns']<row['decision_ns']:raise ValueError('Invalid label timing')
        if (row['provider'],row['symbol'])!=venue or len(row['features'])!=5 or not all(math.isfinite(v) for v in row['features']+[row['return_bps']]):raise ValueError('Invalid checkpoint examples')
        previous=row['decision_ns']
    json.dumps(state,allow_nan=False)
    training.venue=venue;training.examples=copy.deepcopy(examples);training.report=copy.deepcopy(t['report']);training.report['qualified']=False
    training.generation+=1;training.records.clear()
    l=state['ledger']
    for key in ('model','frozen_ns','model_id','resolved','invalid','trades','net_sum','loss_sum','zero_loss_sum'):setattr(ledger,key,copy.deepcopy(l[key]))
    ledger.rows.clear();ledger.rows.extend(l.get('latest',[])[-20:]);ledger.pending=None
    # A process outage cannot count as continuous prospective evaluation.
    ledger.complete=bool(ledger.model is not None);ledger.last_decision=-10**18

class ResearchCheckpoint:
    def __init__(self):
        self.url=os.environ.get('ECOLOGY_CHECKPOINT_DATABASE_URL');self.enabled=bool(self.url);self.future=None;self.last_attempt=-10**18;self.pool=ThreadPoolExecutor(max_workers=1,thread_name_prefix='checkpoint') if self.enabled else None
        self.report=dict(status='configured' if self.enabled else 'disabled_ephemeral',restored_examples=0)
    def connection(self):
        import psycopg
        return psycopg.connect(self.url,connect_timeout=5,sslmode='require')
    def initialize(self,training,ledger):
        if not self.enabled:return
        try:
            with self.connection() as db:
                db.execute('CREATE TABLE IF NOT EXISTS ecology_research_checkpoint (key text PRIMARY KEY, state jsonb NOT NULL)')
                row=db.execute('SELECT state FROM ecology_research_checkpoint WHERE key=%s',(KEY,)).fetchone()
            if row:restore(row[0],training,ledger)
            self.report=dict(status='restored' if row else 'empty',restored_examples=len(training.examples))
        except Exception as error:self.report=dict(status='unavailable',error_type=type(error).__name__,restored_examples=0)
    def write(self,state):
        with self.connection() as db:
            db.execute('INSERT INTO ecology_research_checkpoint(key,state) VALUES(%s,%s::jsonb) ON CONFLICT(key) DO UPDATE SET state=excluded.state',(KEY,json.dumps(state,allow_nan=False)))
        return state['saved_ns']
    def tick(self,training,ledger,now):
        if not self.enabled:return self.report
        if self.future is not None and self.future.done():
            try:self.report.update(status='saved',last_saved_ns=self.future.result())
            except Exception as error:self.report.update(status='unavailable',error_type=type(error).__name__)
            self.future=None
        if self.future is None and now-self.last_attempt>=60_000_000_000:
            self.last_attempt=now;self.future=self.pool.submit(self.write,snapshot(training,ledger))
        return dict(self.report,write_pending=self.future is not None)
