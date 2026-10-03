"""Reproduce the daily evaluation equity/drawdown figure from frozen forecasts."""
import csv,datetime as dt
from pathlib import Path
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from .crossasset_daily_research import portfolio

def run(root):
    root=Path(root);out=root/'docs/crossasset_daily';series={}
    for model in ['btc_only','crossasset']:
        with (out/(model+'_predictions.csv')).open() as f:rows=[r for r in csv.DictReader(f) if r['execution_date']>='2025-07-01']
        p=np.array([float(r['forecast_bps']) for r in rows]);returns=np.array([float(r['target_simple_return']) for r in rows]);stats=portfolio(p,returns,25)
        series[model]=np.r_[100,100*np.cumprod(1+np.array(stats['daily_returns']))]
    series['buy_and_hold']=np.r_[100,100*np.cumprod(1+np.array(portfolio(np.full(len(rows),100),returns,25)['daily_returns']))]
    dates=[dt.date.fromisoformat(rows[0]['execution_date'])]+[dt.date.fromisoformat(r['execution_date'])+dt.timedelta(days=1) for r in rows]
    fig,axes=plt.subplots(2,1,figsize=(10,6),sharex=True,gridspec_kw={'height_ratios':[2,1]},layout='constrained')
    labels={'crossasset':'Ten-coin model','btc_only':'BTC-only model','buy_and_hold':'Hold BTC'}
    colors={'crossasset':'#1976a3','btc_only':'#cc6a35','buy_and_hold':'#64748b'}
    for name in ['crossasset','btc_only','buy_and_hold']:
        v=series[name];axes[0].plot(dates,v,label=labels[name],color=colors[name],lw=1.5);axes[1].plot(dates,100*(v/np.maximum.accumulate(v)-1),color=colors[name],lw=1.3)
    axes[0].axhline(100,color='#94a3b8',ls='--',lw=1,label='Cash');axes[0].set_ylabel('Capital, starting at 100');axes[1].set_ylabel('Drawdown (%)')
    axes[0].set_title('Daily strategy evaluation: losses, recoveries and costs',loc='left',fontsize=14);axes[0].legend(ncol=2,frameon=False,fontsize=9)
    for ax in axes:ax.grid(alpha=.15);ax.spines[['top','right']].set_visible(False)
    axes[1].set_xlabel('July 2025 to August 2026 • 0.25% fee per entry or exit • ideal daily open fills',fontsize=9)
    fig.savefig(out/'EQUITY_EVALUATION.png',dpi=110);fig.savefig(out/'EQUITY_EVALUATION.svg');plt.close(fig)
if __name__=='__main__':
    import sys
    run(sys.argv[1])
