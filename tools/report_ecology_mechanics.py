"""Render the measured ecology report and scientific figure from frozen results."""
import argparse
import json
from pathlib import Path
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np


def number(v):return 'insufficient blocks' if v is None else f'{v:.3f}'
def interval(d):return f"{number(d['mean'])} [{number(d['lower'])}, {number(d['upper'])}]"


def render(results,out):
    results=Path(results);out=Path(out);out.mkdir(parents=True,exist_ok=True)
    r=json.loads((results/'report.json').read_text());audit=json.loads((results/'source_audit.json').read_text())
    hours=r['hours'];n=sum(x['windows'] for x in r['audits'].values());fresh=sum(x['fresh_windows'] for x in r['audits'].values())
    summary={k:v for k,v in r.items() if k!='results'}
    (out/'summary.json').write_text(json.dumps(summary,indent=2)+'\n')
    (out/'source_audit.json').write_text(json.dumps(audit,indent=2)+'\n')
    for h,x in r['results'].items():(out/f'{h}.json').write_text(json.dumps(x,indent=2)+'\n')
    lines=[f'''# Observed market ecology and price reactions

Research completed 2 October 2026. This study measures how observed trading pressure and displayed liquidity changes accompany price changes in the supplied BTCUSDT recordings. It does not identify individual participants, establish causality, or certify a profitable policy.

## What the completed analysis found

The measured distinction is between **aggressive trading pressure that coincides with supportive book changes** and **pressure that coincides with opposing book changes**. Trade volume alone is an incomplete description. Displayed liquidity reinforcement has a positive same-window mean contrast in all six recordings, but exploratory confidence intervals exclude zero in only two. The positive contrasts remain in those two recordings after freshness filtering and changing the bootstrap block length. This supports further study of pressure versus replenishment; it does not establish a universal trading rule.

Best-quote OFI distinguishes the same-window reactions more strongly, but its definition includes quote movements. Its apparent explanatory strength is therefore partly mechanical. The frozen book-only regression fails on 26 May at 15:00, despite strong same-window directional association there: a relationship can retain its direction while its magnitude changes enough to break a calibrated model.

## Source and timing audit

Six selected source hours over two days produced **{n:,} eligible approximately one-second windows**, of which **{fresh:,}** satisfy the additional 250 ms message-age rule. Their summed accepted duration is **{sum(x['recorded_window_seconds'] for x in r['audits'].values())/60:.2f} minutes**. These are discontinuous verified segments, not six continuous hours and not independent samples from many days.

Two local midnight order-book copies were incomplete. The full 8,872,131-byte saved original was recovered and its Parquet footer validated. One generated midday CSV did not match its reconstruction count; it was rebuilt before final analysis. Final reconstructed midday, evening and next-day tapes match every original column and row of the four previously corrected tapes. The study now fails if any generated CSV row count differs from its reconstruction audit.

The raw trade audit found **{sum(x['trade_integrity']['missing_payload_records'] for x in audit.values())} records with order_type=NA, price=0 and quantity=0**. These are treated as unknown trade payloads. **{sum(x.get('missing_trade_payload',0) for x in r['audits'].values())} otherwise eligible windows containing such records were excluded**, rather than assigning zero trading pressure to unknown activity. Existing strategy reports did not apply this new exclusion; their results should not be represented as validation under this stricter observation boundary.

The raw trade files also contain **{sum(x['trade_integrity']['positive_id_gap_steps'] for x in audit.values())} trade-ID gap steps**, all in the 26 May 15:00 recording, spanning **{sum(x['trade_integrity']['missing_trade_ids'] for x in audit.values())} absent IDs**. A window intersecting the receipt interval bracketing such a gap is conservatively rejected. These range exclusions precede the individual missing-payload check; exclusion counts are sequential, not additive overlapping diagnoses.

SHA-256 hashes, source byte sizes, source row counts, sequence reconstruction counts, trade ID integrity and message-age distributions are saved in [source_audit.json](price_mechanics/source_audit.json). Study parameters, fitted coefficients and processed input hashes are in [summary.json](price_mechanics/summary.json).

| Source hour (UTC) | Verified book intervals | Accepted windows | Fresh windows | Missing trade payloads | Windows excluded for missing trades |
|---|---:|---:|---:|---:|---:|''']
    for h in hours:
        a=r['audits'][h];lines.append(f"| {h} | {a['reconstruction']['calibration_intervals']:,} | {a['windows']} | {a['fresh_windows']} | {audit[h]['trade_integrity']['missing_payload_records']} | {a.get('missing_trade_payload',0)} |")
    lines.append(r'''
## Mathematical observation model

Let m be the midpoint of the best bid and ask. The response in basis points is r=10,000 log(m_end/m_start). One basis point is 0.01%. Signed aggressive volume is V=buy BTC−sell BTC, using the recorded buyer-maker flag to infer the aggressor side. Start depth D is displayed bid plus ask quantity within 10 basis points of the start midpoint. Pressure is V/D.

For update n, with bid price b, ask price a and queue sizes qB and qA, the implemented best-quote order-flow imbalance increment is:

$$e_n=1_{b_n\ge b_{n-1}}q^B_n-1_{b_n\le b_{n-1}}q^B_{n-1}-1_{a_n\le a_{n-1}}q^A_n+1_{a_n\ge a_{n-1}}q^A_{n-1}.$$

OFI is the sum of these increments over received update bundles, normalized for regression by the average of the two initial best-quote queue sizes. A bundled update is not a full sequence of individual orders.

Displayed pressure L=(bid additions−bid reductions−ask additions+ask reductions)/D. For buy pressure, bid additions and ask reductions reinforce pressure; ask additions and bid reductions oppose it. Reverse these signs for sell pressure. Reductions do not distinguish executions, cancellations or modifications. The price band is evaluated against each update's pre-midpoint, so moving boundaries and incomplete deeper coverage also affect this measure.

Directional response z=sign(V)r is positive when price moves with the observed aggressive trade direction, negative when it moves against it, and zero when the midpoint is unchanged. All group means and directional probabilities include unchanged outcomes.

High pressure means |V/D| is at or above the 75th percentile among nonzero-pressure windows in 25 May 00:00. Thin depth means D below that first recording's median. These cutoffs, feature normalization and ridge coefficients are frozen before processing subsequent hours. The remaining hours have been inspected in earlier project research, so they are chronological comparisons, not untouched final tests.
''')
    lines.append(f"Frozen high-pressure cutoff: **{r['thresholds']['high_trade_pressure']:.9f}**; thin-depth cutoff: **{r['thresholds']['thin_depth_btc']:.3f} BTC**.")
    lines.append('''
## Price reaction when liquidity reinforces or opposes trade pressure

All rows below condition on high trade pressure. Units are directional midpoint basis points, not executable profit. Brackets are exploratory 95% one-minute block-bootstrap intervals from 1,000 draws. Shared resamples estimate the contrast between conditional means. Intervals are omitted when either group occupies fewer than 10 active blocks.

| Hour | Reinforces: n / mean bps | Opposes: n / mean bps | Reinforces minus opposes, 95% interval | Fresh-only contrast, 95% interval |
|---|---:|---:|---|---|''')
    for h in hours:
        x=r['results'][h];g=x['groups'];a=g['display_reinforces'];b=g['display_opposes'];key='display_reinforces_minus_display_opposes'
        lines.append(f"| {h} | {a['windows']} / {number(a['aligned_mean_bps']['mean'])} | {b['windows']} / {number(b['aligned_mean_bps']['mean'])} | {interval(x['contrasts'][key])} | {interval(x['fresh_contrasts'][key])} |")
    lines.append('''
The contrast is a conditional association. Groups are not matched for trade size, starting imbalance, volatility, hidden liquidity or trader information. It cannot isolate a causal liquidity effect. Thin/deep contrasts are also confounded: the pressure criterion itself already divides by depth. Their mixed signs and sparse thin groups do not support claiming a universal depth multiplier in this sample.

## Same-window directional probabilities

"Book agrees" means OFI has the same sign as aggressive flow; "book opposes" means the opposite sign. This includes information observed during the price move and is a retrospective description. Zero observed events do not establish zero population probability; an empirical bootstrap can give a degenerate zero interval in small samples.

| Hour | Book agrees: n / price moves with flow | Book opposes: n / price moves with flow | High pressure: unchanged midpoint |
|---|---:|---:|---:|''')
    for h in hours:
        g=r['results'][h]['groups'];a=g['book_agrees'];b=g['book_opposes'];c=g['high_trade_pressure']
        lines.append(f"| {h} | {a['windows']} / {a['aligned_probability']['mean']:.1%} | {b['windows']} / {b['aligned_probability']['mean']:.1%} | {c['unchanged_probability']['mean']:.1%} |")
    lines.append('''
Full per-group distributions include 5th/25th/50th/75th/95th percentiles, directional/contrary/unchanged probabilities and block intervals. See the individual hour JSON files in [price_mechanics](price_mechanics).

## Frozen regression and probability diagnostics

The ridge models use alpha=1 and train-only centering/scaling. They explain the already-observed same-window response using (a) trade pressure, (b) OFI pressure, or (c) both plus displayed pressure, initial imbalance, log(1+D), and trade pressure interacted with the thin-depth indicator. OFI contains quote changes; these R² values are not predictive accuracy. Negative R² means the frozen fit is worse than a constant equal to that evaluation hour's realized mean. No-trade/zero-response RMSE is separately saved.

| Hour | Trade-only R² | Book-only R² | Joint R² | Fresh book-only R² |
|---|---:|---:|---:|---:|''')
    for h in hours:
        x=r['results'][h];s=x['regressions'];lines.append(f"| {h} | {number(s['trade_only']['descriptive_r_squared'])} | {number(s['book_only']['descriptive_r_squared'])} | {number(s['joint']['descriptive_r_squared'])} | {number(x['fresh_regressions']['book_only']['descriptive_r_squared'])} |")
    lines.append('''
Three-state sign mutual information measures dependence between negative/zero/positive flow or book pressure and negative/zero/positive return. Each hour also has 200 whole-minute-block shuffles. These are dependence diagnostics, not causal tests or calibrated p-values: exchangeability of different minutes is not established. Same-window OFI dependence is partly built into quote formation. No multiple-comparison correction was applied to the exploratory group tables; none is a pre-registered discovery claim.

## Does the initial pressure keep moving price?

The following responses start **after** the observed one-second window ends. They require a same-episode endpoint within 250 ms of the five-second target and a book path without receipt gaps above 250 ms. They are conditional on observable paths, so missing exits may change the estimate. Future trade missingness is not used to filter a price-only response. A positive estimate here is not net trading profit.

| Hour | Available high-pressure outcomes | Missing outcomes | Next-five-second aligned mean bps, 95% interval |
|---|---:|---:|---|''')
    for h in hours:
        f=r['results'][h]['groups']['high_trade_pressure']['forward_5s'];lines.append(f"| {h} | {f['available']} | {f['missing']} | {interval(f['aligned_mean_bps'])} |")
    lines.append('''
Only the final recording's overall high-pressure five-second interval excludes zero on the positive side; this exploratory result has substantial missingness and no independent final validation. The other five intervals cross zero. It is evidence to investigate persistence and absorption, not grounds to deploy a profitable strategy.

## How this changes the ecology machinery

The observational baseline should expose: aggressive buy/sell pressure, displayed liquidity reinforcement/opposition, best-quote imbalance, initial depth, observed price response, post-window response and data confidence. A simulator should reproduce their **joint distributions and state transitions**, rather than merely produce a visually moving price.

Operational regime labels can be defined without inventing actor identities: pressure with reinforcement; pressure with opposing liquidity; pressure with unchanged midpoint; and opposing price reaction. "Absorption" and "withdrawal" are hypotheses attached to these observations, not proven institutional intent. Market makers and other participants can add or remove liquidity; anonymous L2 cannot attribute those actions to named categories or recover psychology.

The measured evidence supports investigating state-dependent event intensities and replenishment. It does not justify importing a universal impact coefficient, fitting many models until one wins, or transferring Binance historical calibration directly to the live Coinbase feed. Options/GEX additionally require a chain, volatility surface and stated signed inventory assumptions; those are absent from these six BTCUSDT recordings. Macro bubbles and auctions remain separate research branches.

## Primary research and applicability

* [Cont, Kukanov & Stoikov — The Price Impact of Order Book Events](https://arxiv.org/pdf/1011.6402): supplies the best-quote OFI construction and a hypothesis about depth-dependent impact. Its US-equity results are not calibration for BTCUSDT.
* [Tóth et al. — How does the market react to your order flow?](https://arxiv.org/pdf/1104.0587): motivates studying the interaction of trading pressure and liquidity provision. Its broker-identified data support participant decomposition that our anonymous recordings cannot reproduce.
* [Huang, Lehalle & Rosenbaum — The queue-reactive model](https://arxiv.org/pdf/1312.0563): motivates event intensities conditional on queue state. A faithful queue-reactive simulator still needs calibrated intensities, price-transition rules and validation against empirical distributions; this report does not claim to have implemented that entire model.
* [Gould & Bonart — Queue Imbalance as a One-Tick-Ahead Price Predictor](https://arxiv.org/abs/1512.03492): distinguishes a queue-state conditional probability from deterministic prediction. Different tick structures and markets require separate evaluation; their stock results are not imported as Bitcoin probabilities.

The earlier uploaded-paper integration remains documented in [OCTOBER_RESEARCH_INTEGRATION.md](OCTOBER_RESEARCH_INTEGRATION.md). This study adds microstructure measurements; it does not claim reproduction of every uploaded strategy or a complete model of every participant.

## Reproduction and validation

With numpy, pyarrow, zstandard and matplotlib installed, reconstruct the six supplied books using `python -m src.simulation.book_changes <book files> --out data/processed/mechanics_study_states`. Use the full recovered midnight book, not its incomplete local copies. Run:

```bash
python -m src.simulation.mechanics_input_audit --raw-dir <originals> --recovered-dir <recovered-originals> --states-dir data/processed/mechanics_study_states --out data/processed/ecology_price_mechanics/source_audit.json
python -m src.simulation.ecology_price_mechanics --states-dir data/processed/mechanics_study_states --raw-dir <originals> --out data/processed/ecology_price_mechanics
python tools/report_ecology_mechanics.py --results data/processed/ecology_price_mechanics --out docs/price_mechanics
python -m unittest discover -s tests -p 'test_simulation*.py'
```

Tests cover quote-price/queue OFI changes, exact receipt boundaries, excluded gaps/crossed books, missing trade payload and trade-ID-gap exclusion, conditional group definitions, block contrasts and information sanity checks. Whole-source reconstruction parity was checked for all four previously corrected tapes. Raw files are not redistributed; original source hashes let the owner verify reproduction. Window CSVs are generated locally by the analysis command.

![Measured ecology and price reactions](price_mechanics/ecology_price_mechanics.svg)
''')
    (out.parent/'ECOLOGY_PRICE_MECHANICS.md').write_text('\n'.join(lines)+'\n')
    plt.rcParams.update({'font.size':10,'svg.fonttype':'none'})
    fig,axes=plt.subplots(2,2,figsize=(15,10));labels=[h.replace('2026-','').replace('_','\n') for h in hours];ix=np.arange(len(hours))
    for name,color,offset in [('display_reinforces','#216e87',-.14),('display_opposes','#b76b33',.14)]:
        stats=[r['results'][h]['groups'][name]['aligned_mean_bps'] for h in hours]
        vals=np.array([s['mean'] for s in stats]);lo=np.array([s['lower'] if s['lower'] is not None else s['mean'] for s in stats]);hi=np.array([s['upper'] if s['upper'] is not None else s['mean'] for s in stats])
        axes[0,0].errorbar(ix+offset,vals,yerr=[vals-lo,hi-vals],fmt='o',capsize=3,color=color,label=name.replace('display_','').capitalize())
    axes[0,0].set(title='Price reaction during heavy pressure',ylabel='Directional midpoint move (bps)');axes[0,0].legend()
    bottom=np.zeros(len(hours))
    for key,color,label in [('aligned_probability','#216e87','With flow'),('unchanged_probability','#c9d1d8','Unchanged'),('opposite_probability','#b76b33','Against flow')]:
        vals=np.array([r['results'][h]['groups']['high_trade_pressure'][key]['mean']*100 for h in hours]);axes[0,1].bar(ix,vals,bottom=bottom,color=color,label=label);bottom+=vals
    axes[0,1].set(title='Price often stays unchanged',ylabel='High-pressure windows (%)',ylim=(0,105));axes[0,1].legend(fontsize=9)
    for kind,color,offset in [('trade_only','#b76b33',-.22),('book_only','#216e87',0),('joint','#8063a6',.22)]:
        axes[1,0].bar(ix+offset,[r['results'][h]['regressions'][kind]['descriptive_r_squared'] for h in hours],width=.22,color=color,label=kind.replace('_',' '))
    axes[1,0].set(title='Frozen explanatory fits do not transfer uniformly',ylabel='Same-window R² (not forecast accuracy)');axes[1,0].legend(fontsize=9)
    stats=[r['results'][h]['groups']['high_trade_pressure']['forward_5s']['aligned_mean_bps'] for h in hours];vals=np.array([s['mean'] for s in stats]);lo=np.array([s['lower'] for s in stats]);hi=np.array([s['upper'] for s in stats])
    axes[1,1].errorbar(ix,vals,yerr=[vals-lo,hi-vals],fmt='o',capsize=3,color='#216e87');axes[1,1].set(title='After the pressure: next five seconds',ylabel='Directional midpoint move (bps)')
    for ax in axes.flat:ax.set_xticks(ix,labels);ax.axhline(0,color='#555',linewidth=.7);ax.grid(axis='y',alpha=.15);ax.spines[['top','right']].set_visible(False)
    fig.suptitle(f'Observed market ecology → price response | {n:,} audited windows',fontsize=19,y=.98)
    fig.text(.04,.02,'Six selected, discontinuous BTCUSDT recordings. Bars/dots describe observations; no actor identities or causal effects.\nIntervals: exploratory 95% one-minute block bootstrap; future paths have substantial missingness. 1 bps = 0.01%.',fontsize=10)
    fig.tight_layout(rect=(0,.07,1,.95));fig.savefig(out/'ecology_price_mechanics.svg');fig.savefig(out/'ecology_price_mechanics.png',dpi=150);plt.close(fig)


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--results',required=True);p.add_argument('--out',required=True);a=p.parse_args();render(a.results,a.out)
