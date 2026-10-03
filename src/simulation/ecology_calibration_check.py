"""Instrument synthetic order events and compare regime summaries, without fitting agents."""
import argparse
import hashlib
import json
from pathlib import Path
import math
import numpy as np
from .ecology import Book,TICK,run,common_flow
from .ecology_regime_dynamics import summarize,STATES


class ObservedBook(Book):
    def begin_observation(self,second):
        bid=self.best('bid');ask=self.best('ask');mid=(bid+ask)*TICK/2
        self.observed=dict(second=second,start_mid=mid,start_depth=self.near_depth(mid),buy=0.,sell=0.,bid_add=0.,bid_remove=0.,ask_add=0.,ask_remove=0.)
    def near_depth(self,mid):
        return sum(sum(owners.values()) for side in ('bid','ask') for price,owners in self.levels(side).items()
                   if (side=='bid' and price*TICK>=mid*.999) or (side=='ask' and price*TICK<=mid*1.001))
    def snapshot(self):
        mid=(self.best('bid')+self.best('ask'))*TICK/2
        return mid,{side:{price:sum(owners.values()) for price,owners in self.levels(side).items()} for side in ('bid','ask')}
    def record_changes(self,before):
        if not hasattr(self,'observed'):return
        mid,old=before
        for side in ('bid','ask'):
            after={p:sum(o.values()) for p,o in self.levels(side).items()}
            for p in old[side].keys()|after.keys():
                if not ((side=='bid' and p*TICK>=mid*.999) or (side=='ask' and p*TICK<=mid*1.001)):continue
                delta=after.get(p,0.)-old[side].get(p,0.)
                self.observed[side+('_add' if delta>0 else '_remove')]+=abs(delta)
    def cancel(self,maker,fraction):
        before=self.snapshot();value=super().cancel(maker,fraction);self.record_changes(before);return value
    def replenish(self,maker,fraction):
        before=self.snapshot();value=super().replenish(maker,fraction);self.record_changes(before);return value
    def execute(self,side,requested):
        before=self.snapshot();result=super().execute(side,requested);self.record_changes(before)
        if hasattr(self,'observed'):self.observed[side]+=result[0]
        return result
    def state(self,*args,**kwargs):
        row=super().state(*args,**kwargs)
        if hasattr(self,'observed'):
            o=self.observed;depth=o['start_depth'];signed=o['buy']-o['sell']
            row.update(signed_btc=signed,trade_pressure=signed/depth,
                       display_pressure=(o['bid_add']-o['bid_remove']-o['ask_add']+o['ask_remove'])/depth,
                       move_bps=10000*math.log(row['mid']/o['start_mid']))
        return row


def distribution(summary):
    n=summary['windows'];return np.array([summary['regimes'][s]['windows']/n for s in STATES])


def compare(sim,real):
    a=distribution(sim);b=distribution(real)
    sc=np.array(sim['transition_counts'],dtype=float);rc=np.array(real['transition_counts'],dtype=float)
    row_distances={}
    for i,state in enumerate(STATES):
        row_distances[state]=float(np.abs(sc[i]/sc[i].sum()-rc[i]/rc[i].sum()).sum()/2) if sc[i].sum() and rc[i].sum() else None
    return dict(occupancy_total_variation=float(np.abs(a-b).sum()/2),transition_row_total_variation=row_distances,
                observed_run_median_difference_seconds={state:(sim['regimes'][state]['median_observed_run_seconds']-real['regimes'][state]['median_observed_run_seconds'])
                    if sim['regimes'][state]['median_observed_run_seconds'] is not None and real['regimes'][state]['median_observed_run_seconds'] is not None else None for state in STATES},
                interpretation='Distances 0=matching empirical proportions, 1=disjoint. Sparse rows and unequal coverage limit inference. No pass/fail tolerance has been validated.')


def check(config,reference,out):
    params=json.loads(Path(config).read_text())['calibration_from_valid_samples'];ref=json.loads(Path(reference).read_text());reports={}
    for seed in (7,19,43):
        flow=common_flow(params,seed)
        for withdrawal in (False,True):
            rows,_=run(params,flow,withdrawal,book_factory=ObservedBook)
            # Shock and withdrawal are intentional interventions, kept separate.
            scenarios={'before_intervention':[r for r in rows if 0<=r['second']<120],
                       'full_intervention_run':[r for r in rows if r['second']>=0]}
            for segment,selected in scenarios.items():
                windows=[dict(r,start_ns=r['second']*1000000000,end_ns=(r['second']+1)*1000000000,episode=1,duration_seconds=1.) for r in selected]
                summary,_,_=summarize(windows,ref['pressure_cut'])
                key=f'{seed}_{"withdrawal" if withdrawal else "normal"}_{segment}'
                reports[key]=dict(seed=seed,withdrawal=withdrawal,segment=segment,summary=summary,
                                 comparisons={h:compare(summary,x['summary']) for h,x in ref['results'].items()})
    result=dict(status='synthetic_simulator_calibration_diagnostic_not_qualified',states=list(STATES),reports=reports,
                config_sha256=hashlib.sha256(Path(config).read_bytes()).hexdigest(),reference_sha256=hashlib.sha256(Path(reference).read_bytes()).hexdigest(),
                limitations=['Background flow, maker posting/reductions and intervention parameters remain assumed, not fitted.',
                    'Pre-intervention normal and withdrawal runs share identical flow and behavior and are not independent replications.',
                    'Synthetic snapshots are captured per method call; observed real data contains received L2 bundles. Event aggregation and timing differ.',
                    'Regime definitions use matched quantity units and near-touch bands, but unknown real deeper liquidity, coverage and timing differ.',
                    'Forced shock/withdrawal runs are counterfactual stress demonstrations, not samples from natural historical frequencies.',
                    'Distances are descriptive; no statistically validated equivalence tolerance, event simulator qualification or profitable policy is established.'])
    out=Path(out);out.mkdir(parents=True,exist_ok=True);(out/'report.json').write_text(json.dumps(result,indent=2)+'\n');return result


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--config',required=True);p.add_argument('--reference',required=True);p.add_argument('--out',required=True);a=p.parse_args();check(a.config,a.reference,a.out)
