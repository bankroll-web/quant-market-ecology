"""Chronological rolling LASSO: BTC-only versus crossasset, daily long/flat paper test."""
import csv,hashlib,json,math,warnings
from pathlib import Path
import numpy as np
from sklearn.exceptions import ConvergenceWarning
from sklearn.linear_model import Lasso
from sklearn.model_selection import TimeSeriesSplit
from sklearn.preprocessing import StandardScaler
from .crossasset_daily_data import SYMBOLS

WINDOW=714
ALPHAS=(.1,1.,5.)

def load(root):
    series={}
    for s in SYMBOLS:
        with (Path(root)/'data/processed/crossasset_daily'/(s+'.csv')).open() as f:rows=list(csv.DictReader(f))
        series[s]=rows
    dates=[r['date'] for r in series[SYMBOLS[0]]]
    if any([r['date'] for r in series[s]]!=dates for s in SYMBOLS):raise ValueError('Clock mismatch')
    features=[]
    for s in SYMBOLS:
        rows=series[s];close=np.array([float(r['close']) for r in rows]);h=np.array([float(r['high']) for r in rows]);l=np.array([float(r['low']) for r in rows]);q=np.array([float(r['quote_volume']) for r in rows]);ret=np.r_[np.nan,np.diff(np.log(close))]
        features.append(np.column_stack([10000*ret,np.log(q),np.log(h/l)**2/(4*np.log(2)),np.abs(ret)/q*1e8]))
    values=np.stack(features,axis=1);btc_open=np.array([float(r['open']) for r in series['BTCUSDT']]);ns=np.array([int(r['open_ns']) for r in series['BTCUSDT']],dtype=np.int64)
    indices=np.arange(7,len(dates)-3)
    x=np.array([values[i-np.arange(7)].transpose(1,0,2).reshape(-1) for i in indices]);y=np.array([10000*math.log(btc_open[i+3]/btc_open[i+2]) for i in indices])
    return dates,ns,indices,x,y,btc_open

def fit_model(x,y,alpha):
    scaler=StandardScaler().fit(x);model=Lasso(alpha=alpha,max_iter=10000,tol=1e-5)
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter('always',ConvergenceWarning);model.fit(scaler.transform(x),y)
    if any(issubclass(w.category,ConvergenceWarning) for w in caught):raise ValueError('LASSO did not converge; no result promotion')
    return scaler,model

def choose_alpha(x,y):
    scores={}
    for a in ALPHAS:
        mse=[]
        for tr,te in TimeSeriesSplit(n_splits=5,gap=2).split(x):
            scaler,model=fit_model(x[tr],y[tr],a);p=model.predict(scaler.transform(x[te]));mse.append(float(np.mean((p-y[te])**2)))
        scores[str(a)]=dict(mse=float(np.mean(mse)),fold_mse=mse)
    return min(ALPHAS,key=lambda a:scores[str(a)]['mse']),scores

def train_indices(i,indices,ns):
    eligible=np.flatnonzero(indices+3<=i+1)[-WINDOW:]
    if len(eligible)!=WINDOW:raise ValueError('Incomplete training window')
    if np.any(ns[indices[eligible]+3]>ns[i+1]):raise ValueError('Unresolved training label')
    return eligible

def portfolio(pred,returns,cost_side_bps=25,threshold=25):
    pos=0;equity=1.;path=[1.];turnover=0;exposure=0;daily=[]
    for p,r in zip(pred,returns):
        new=1 if p>threshold else 0 if p<-threshold else pos
        factor=(1-cost_side_bps/10000)**abs(new-pos)*(1+new*r)
        turnover+=abs(new-pos);pos=new;exposure+=pos;equity*=factor;path.append(equity);daily.append(factor-1)
    if pos:
        factor=1-cost_side_bps/10000;equity*=factor;path[-1]=equity;daily[-1]=(1+daily[-1])*factor-1;turnover+=1
    path=np.array(path);daily=np.array(daily)
    return dict(net_return_pct=100*(equity-1),max_drawdown_pct=100*float(np.min(path/np.maximum.accumulate(path)-1)),annualized_daily_sharpe=float(np.mean(daily)/np.std(daily,ddof=1)*np.sqrt(365)) if len(daily)>1 and np.std(daily)>0 else None,executed_sides=turnover,long_exposure_fraction=exposure/len(returns),daily_returns=daily.tolist())

def stationary_ci(values,seed=91):
    values=np.asarray(values);rng=np.random.default_rng(seed);n=len(values);means=[]
    for _ in range(5000):
        j=int(rng.integers(n));acc=0.
        for k in range(n):
            if k and rng.random()<1/7:j=int(rng.integers(n))
            acc+=values[j];j=(j+1)%n
        means.append(acc/n)
    return list(map(float,np.quantile(means,[.025,.975])))

def run(root):
    root=Path(root);dates,ns,indices,x,y,opens=load(root)
    configurations={'btc_only':np.arange(28),'crossasset':np.arange(280)}
    predictions={};selection={};coefficients={}
    for name,columns in configurations.items():
        a,scores=choose_alpha(x[:WINDOW,columns],y[:WINDOW]);selection[name]=dict(alpha=a,training_fold_scores=scores)
        pred=[];rows=[]
        for k,i in enumerate(indices):
            date=dates[i+2]
            if not('2025-01-01'<=date<='2026-08-30'):continue
            tr=train_indices(i,indices,ns);scaler,model=fit_model(x[tr][:,columns],y[tr],a)
            p=float(model.predict(scaler.transform(x[k:k+1,columns]))[0]);pred.append(dict(execution_date=date,feature_date=dates[i],observation_available_ns=int(ns[i+1]),execution_ns=int(ns[i+2]),target_available_ns=int(ns[i+3]),max_training_label_available_ns=int(ns[indices[tr[-1]]+3]),forecast_bps=p,target_log_return_bps=float(y[k]),target_simple_return=float(opens[i+3]/opens[i+2]-1),training_mean_bps=float(y[tr].mean())))
            if k==len(indices)-1:coefficients[name]=dict(nonzero=int(np.sum(model.coef_!=0)),intercept_bps=float(model.intercept_))
        predictions[name]=pred
    report=dict(status='daily_crossasset_development_and_chronological_evaluation',qualified=False,orders_enabled=False,rolling_window=WINDOW,selection=selection,final_model=coefficients,segments={})
    for name,start,end in [('development','2025-01-01','2025-06-30'),('evaluation','2025-07-01','2026-08-30')]:
        selected={m:[r for r in rows if start<=r['execution_date']<=end] for m,rows in predictions.items()};section={}
        for model,rows in selected.items():
            if not rows:raise ValueError('Empty segment')
            p=np.array([r['forecast_bps'] for r in rows]);yhat=np.array([r['target_log_return_bps'] for r in rows]);mean=np.array([r['training_mean_bps'] for r in rows]);ret=np.array([r['target_simple_return'] for r in rows])
            costs={}
            for cost in (5,10,25):
                strategy=portfolio(p,ret,cost);buyhold=portfolio(np.full(len(ret),100),ret,cost)
                daily=np.array(strategy.pop('daily_returns'));buyhold.pop('daily_returns')
                years={}
                for year in sorted({r['execution_date'][:4] for r in rows}):
                    mask=np.array([r['execution_date'].startswith(year) for r in rows]);ds=daily[mask]
                    years[year]=dict(days=int(mask.sum()),strategy_net_return_pct=float(100*(np.prod(1+ds)-1)))
                costs[str(cost)]=dict(strategy=strategy,buy_and_hold=buyhold,year_contributions=years)
            section[model]=dict(days=len(rows),first=rows[0]['execution_date'],last=rows[-1]['execution_date'],forecast_mse=float(np.mean((p-yhat)**2)),zero_mse=float(np.mean(yhat*yhat)),training_mean_mse=float(np.mean((mean-yhat)**2)),forecast_range_bps=[float(p.min()),float(p.max())],cost_per_side_bps=costs)
        a=selected['btc_only'];b=selected['crossasset'];d=np.array([(rb['forecast_bps']-rb['target_log_return_bps'])**2-(ra['forecast_bps']-ra['target_log_return_bps'])**2 for ra,rb in zip(a,b)])
        section['crossasset_minus_btc_squared_error']=dict(mean=float(d.mean()),stationary_bootstrap_95_ci=stationary_ci(d),block_length_mean_days=7,resamples=5000,seed=91)
        section['cash_net_return_pct']=0.
        report['segments'][name]=section
    report['limits']=['Binance daily USDT spot klines differ from source marketwide USD series; adaptation, not faithful replication.','Daily market-state features are not identified participant behavior. No causal interpretation.','Chronological evaluation is new to this recipe but some dates were inspected in earlier project research. Rolling fits learn prior resolved evaluation outcomes by the fixed protocol.','Ideal daily open fills and per-side fee proxy omit actual spread, impact, size and stablecoin risk. Long/flat only.','No rule tuning after evaluation. Two models and three cost sensitivities disclosed. No independent live validation or strategy qualification.']
    out=root/'docs/crossasset_daily';(out/'RESULTS.json').write_text(json.dumps(report,indent=2)+'\n')
    for model,rows in predictions.items():
        with (out/(model+'_predictions.csv')).open('w') as f:
            w=csv.DictWriter(f,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)
    print(json.dumps(report,indent=2));return report
if __name__=='__main__':
    import sys
    run(sys.argv[1])
