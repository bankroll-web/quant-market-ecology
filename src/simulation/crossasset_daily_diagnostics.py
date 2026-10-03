"""Post-result attribution of extreme forecasts; no strategy rule changes."""
import csv,json
from pathlib import Path
import numpy as np
from .crossasset_daily_data import SYMBOLS
from .crossasset_daily_research import load,train_indices,fit_model,portfolio,stationary_ci

def run(root):
    root=Path(root);dates,ns,indices,x,y,opens=load(root);report=json.loads((root/'docs/crossasset_daily/RESULTS.json').read_text());names=[f'{s}:lag{lag}:{v}' for s in SYMBOLS for lag in range(7) for v in ['return_bps','log_quote_volume','parkinson_variance','amihud']];diagnostics={}
    for model,cols in [('btc_only',np.arange(28)),('crossasset',np.arange(280))]:
        with (root/'docs/crossasset_daily'/(model+'_predictions.csv')).open() as f:rows=list(csv.DictReader(f))
        largest=max(rows,key=lambda r:abs(float(r['forecast_bps'])));i=dates.index(largest['feature_date']);k=int(np.where(indices==i)[0][0]);tr=train_indices(i,indices,ns);scaler,fitted=fit_model(x[tr][:,cols],y[tr],report['selection'][model]['alpha']);z=scaler.transform(x[k:k+1,cols])[0];contributions=z*fitted.coef_;order=np.argsort(-np.abs(contributions))[:10]
        diagnostics[model]=dict(execution_date=largest['execution_date'],forecast_bps=float(largest['forecast_bps']),target_bps=float(largest['target_log_return_bps']),intercept_bps=float(fitted.intercept_),sum_contributions_bps=float(contributions.sum()),outside_training_range_features=int(largest['outside_training_range_features']),top_contributions=[dict(feature=names[int(cols[j])],contribution_bps=float(contributions[j]),training_standard_deviations=float(z[j])) for j in order])
        ev=[r for r in rows if r['execution_date']>='2025-07-01'];p=np.array([float(r['forecast_bps']) for r in ev]);r=np.array([float(r['target_simple_return']) for r in ev]);gross=portfolio(p,r,0);n=gross['executed_sides'];equity=1+gross['net_return_pct']/100
        diagnostics[model]['daily_log_return_uncertainty']={}
        for cost in (5,25):
            pnl=portfolio(p,r,cost);logs=10000*np.log1p(pnl['daily_returns'])
            diagnostics[model]['daily_log_return_uncertainty'][str(cost)]=dict(mean_bps=float(logs.mean()),stationary_bootstrap_95_ci_bps=stationary_ci(logs),resamples=5000,mean_block_days=7,seed=91)
        diagnostics[model]['evaluation_zero_cost_return_pct']=gross['net_return_pct'];diagnostics[model]['evaluation_break_even_cost_per_side_bps']=10000*(1-equity**(-1/n)) if n and equity>1 else None
    result=dict(status='post_result_diagnostics_not_candidate_selection',qualified=False,models=diagnostics,limits=['Attributions describe the fitted linear formula, not causal effects of a cryptocurrency on BTC.','Break-even cost assumes the same idealized daily open fills and signal path; includes no measured venue spread or impact.','Return intervals are exploratory, conditional on the fitted forecast path; bootstrap does not refit the models or adjust for model/cost comparisons.', 'No model feature, penalty or strategy rule is changed after seeing these outcomes.'])
    (root/'docs/crossasset_daily/DIAGNOSTICS.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2));return result
if __name__=='__main__':
    import sys
    run(sys.argv[1])
