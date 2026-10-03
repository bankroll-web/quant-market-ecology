"""Research screening gate; never authorizes trades or live model promotion."""
import argparse,json
from pathlib import Path
RULES={'version':'strategy-evidence-v1','minimum_validation_trades':30,'minimum_active_validation_days':7,'required_validation_mean_net_bps_day':0,'required_daily_bootstrap_lower_bps_day':0,'require_log_loss_below_constant_baseline':True,'scope':'Prospective screening convention, not a proof of independence or profitability. Applied retrospectively to v1 only as a diagnostic.'}

def screen(candidate,metric):
 reasons=[]
 if candidate.get('validation_trades',0)<RULES['minimum_validation_trades']:reasons.append('too_few_validation_trades')
 if candidate.get('validation_active_days',0)<RULES['minimum_active_validation_days']:reasons.append('insufficient_active_day_evidence')
 if candidate.get('validation_bps_day',0)<=0:reasons.append('nonpositive_validation_net_return')
 ci=candidate.get('validation_daily_bootstrap_95_ci')
 if not isinstance(ci,list) or len(ci)!=2:reasons.append('missing_validation_uncertainty_estimate')
 elif ci[0]<=0:reasons.append('validation_lower_confidence_bound_not_positive')
 if metric is None:reasons.append('missing_baseline_comparison')
 elif metric['log_loss']>=metric['baseline_log_loss']:reasons.append('forecast_does_not_beat_constant_baseline')
 return {'candidate':candidate,'passed_screen':not reasons,'reasons':reasons,'qualified':False,'orders_enabled':False}

def audit(source,out):
 r=json.loads(source.read_text());metrics={(m['horizon'],m['model']):m for m in r['metrics'] if m['split']=='validation'}
 rows=[screen(c,metrics.get((c['horizon'],c['model']))) for c in r['validation_candidates']]
 result={'rules':RULES,'source':str(source),'candidate_count':len(rows),'passing_candidates':sum(x['passed_screen'] for x in rows),'candidates':rows,'status':'WAIT','qualified':False,'orders_enabled':False,'limits':['This audit does not retrain models or reinterpret August evaluation as untouched.','Prior run omitted active-day and uncertainty evidence for validation candidates; absent evidence fails the screen.','Thirty trades and seven active days are screening conventions, not adequate evidence on their own.','Passing this screen would permit independent evaluation, never real-money execution.']}
 out.mkdir(parents=True,exist_ok=True);(out/'RESULTS.json').write_text(json.dumps(result,indent=2)+'\n');(out/'RULES.json').write_text(json.dumps(RULES,indent=2)+'\n');print(json.dumps({'candidates':len(rows),'passing':result['passing_candidates'],'status':result['status']}))
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--source',type=Path,default=Path('docs/long_horizon_flow/RESULTS.json'));p.add_argument('--out',type=Path,default=Path('docs/strategy_evidence_gate'));a=p.parse_args();audit(a.source,a.out)
