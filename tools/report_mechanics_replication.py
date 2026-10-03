"""Write a readable report for the frozen additional-period replication."""
import argparse
import json
from pathlib import Path


def interval(d):
    f=lambda x:'not estimated' if x is None else f'{x:.3f}'
    return f"{f(d['mean'])} [{f(d['lower'])}, {f(d['upper'])}]"


def render(source,out):
    r=json.loads(Path(source).read_text());out=Path(out);out.mkdir(parents=True,exist_ok=True)
    n=sum(x['windows'] for x in r['audits'].values());fresh=sum(x['fresh_windows'] for x in r['audits'].values())
    summary={k:v for k,v in r.items() if k!='results'}
    (out/'summary.json').write_text(json.dumps(summary,indent=2)+'\n')
    for h,x in r['results'].items():(out/f'{h}.json').write_text(json.dumps(x,indent=2)+'\n')
    lines=[f'''# Frozen ecology replication: two additional historical periods

Completed 3 October 2026 (South Africa). **The liquidity reinforcement association replicated in both additional recordings; the frozen explanatory regression failed severely in one.** This separates a repeated observation from a transferable quantitative calibration.

## What was frozen

The first study's 25 May 00:00 pressure threshold, thin-depth cutoff, all three ridge fits, normalization, observation windows, freshness rule and bootstrap procedures were retained. No fitting, threshold search, event exclusion chosen from outcomes, or policy promotion occurred. Baseline commit: `{r['baseline_commit']}`. The executable replication checks the baseline JSON's SHA-256 and both observation/reconstruction source-file hashes before running.

These 03:00 and 09:00 recordings come from the same historical two-day archive. They add two periods outside the six-recording study, **not new contiguous days**. Other earlier project work may have inspected them; they are not certified untouched final tests. They are also earlier than some existing comparison hours, although later than the 25 May training hour.

## Source integrity and observation boundary

The 03:00 book was recovered from its saved original Parquet. The 09:00 book was recovered as a 255,620,367-byte legacy CSV and streamed into Parquet. Nanosecond timestamps were read directly as int64; update IDs written with decimal `.0` notation were parsed as exact decimals and safely cast to integers. This preserves the supplied CSV representation, but cannot restore precision or provenance lost before the CSV was created. Structural footer/row-count checks and the same sequence replay were applied. Previously computed feature files were not used.

The two source trade files have no duplicate IDs, backward receipt steps or missing-ID gaps. They contain **{sum(x['trade_integrity']['missing_payload_records'] for x in r['source_audit'].values())} zero-price/zero-quantity NA payload records**. The study rejected **{sum(x.get('missing_trade_payload',0) for x in r['audits'].values())} otherwise eligible windows containing those records**. Source hashes, reconstruction counts, conversion provenance and timing quantiles are in [summary.json](mechanics_replication/summary.json).

The final sample contains **{n:,} approximately one-second windows**, with **{fresh:,}** satisfying the additional 250 ms message-age restriction. Accepted durations total **{sum(x['recorded_window_seconds'] for x in r['audits'].values())/60:.2f} minutes**, spread across discontinuous verified segments.

| Period, UTC | Accepted windows | Fresh windows | Reconstructed book intervals |
|---|---:|---:|---:|''']
    for h in r['hours']:
        a=r['audits'][h];lines.append(f"| {h} | {a['windows']} | {a['fresh_windows']} | {r['source_audit'][h]['reconstruction']['calibration_intervals']:,} |")
    lines.append('''
## Repeated ecology observation

Condition on the **original frozen high-pressure threshold**. A positive directional midpoint response means movement with aggressive trading pressure. Displayed reinforcement means bid additions/ask reductions during buy pressure, or ask additions/bid reductions during sell pressure. Opposition reverses those signs. These are anonymous displayed changes, not identified market-maker actions. Reductions cannot be separated into cancellations and executions.

| Period | Reinforces: n / mean bps | Opposes: n / mean bps | Difference, exploratory 95% interval | Fresh-only difference, 95% interval |
|---|---:|---:|---|---|''')
    key='display_reinforces_minus_display_opposes'
    for h,x in r['results'].items():
        a=x['groups']['display_reinforces'];b=x['groups']['display_opposes']
        lines.append(f"| {h} | {a['windows']} / {a['aligned_mean_bps']['mean']:.3f} | {b['windows']} / {b['aligned_mean_bps']['mean']:.3f} | {interval(x['contrasts'][key])} | {interval(x['fresh_contrasts'][key])} |")
    lines.append('''
Both positive contrasts exclude zero under the one-minute block bootstrap and remain positive with intervals excluding zero under 30-second and 120-second blocks and the freshness subset. Confidence intervals use 1,000 draws, preserve shared block resamples between groups, and are exploratory rather than multiple-comparison adjusted. Group sizes, trading magnitude, volatility and hidden liquidity are not matched. A same-window conditional association does not establish a causal liquidity effect or a trading edge.

| Period | Price moves with pressure when liquidity reinforces | When liquidity opposes | High-pressure midpoint unchanged |
|---|---:|---:|---:|''')
    for h,x in r['results'].items():
        g=x['groups'];lines.append(f"| {h} | {g['display_reinforces']['aligned_probability']['mean']:.1%} | {g['display_opposes']['aligned_probability']['mean']:.1%} | {g['high_trade_pressure']['unchanged_probability']['mean']:.1%} |")
    lines.append('''
## Frozen regression failure and its mechanism

These fits explain a response already observed during the same window; they do not forecast future price. Best-quote OFI includes quote movement. Negative R² indicates performance worse than the evaluation period's realized constant mean.

| Period | Trade-only R² | Book-only R² | Joint R² | Fresh book-only R² |
|---|---:|---:|---:|---:|''')
    for h,x in r['results'].items():
        s=x['regressions'];lines.append(f"| {h} | {s['trade_only']['descriptive_r_squared']:.3f} | {s['book_only']['descriptive_r_squared']:.3f} | {s['joint']['descriptive_r_squared']:.3f} | {x['fresh_regressions']['book_only']['descriptive_r_squared']:.3f} |")
    d=r['results']['2026-05-26_03']['book_fit_failure_diagnostic'];w=d['worst_windows'][0]
    lines.append(f'''
At 03:00, the worst 1% of windows account for **{d['worst_one_percent_squared_error_fraction']:.1%} of the book-only fit's squared error**. Normalized OFI has standard deviation **{d['ofi_pressure_std']:.2f}**, versus **{d['training_ofi_pressure_std']:.2f}** in training. In the largest-error window, initial average best-quote depth is **{w['start_top_depth_btc']:.3f} BTC**; accumulated OFI divided by this small initial queue is **{w['ofi_pressure']:.2f}**. The fixed linear calibration assigns a **{w['frozen_explanatory_fit_bps']:.2f} bps** move, while the observed move is **{w['move_bps']:.3f} bps**. That window passes the freshness test.

This is a demonstrated **extrapolation/normalization failure**: a small initial queue can create an extreme ratio while liquidity evolves within the window. It does not show that the observed book is meaningless. The diagnostic was added after inspecting the failure; no extreme windows were removed and no replacement fit was selected. A future bounded or nonlinear response model, dynamic depth treatment and robust calibration require a separate frozen comparison on additional data.

## Subsequent price response

| Period | Five-second outcomes available / missing | Next-five-second aligned mean bps, exploratory 95% interval |
|---|---:|---|''')
    for h,x in r['results'].items():
        f=x['groups']['high_trade_pressure']['forward_5s'];lines.append(f"| {h} | {f['available']} / {f['missing']} | {interval(f['aligned_mean_bps'])} |")
    lines.append('''
Both overall high-pressure five-second intervals cross zero. The reinforcing-liquidity subgroup at 03:00 has a positive exploratory interval, but subgroup inspection, missing paths and absent execution costs preclude calling it a validated trade. Future price responses condition on verified observable book paths; censoring may bias the distributions.

## Consequence for development

Across the original six periods and these two additions, the reinforcement mean contrast is positive in all eight, with exploratory one-minute intervals excluding zero in four. These are dependent observations from only two days, not eight independent replications across market regimes.

Keep the observational ecology layer: trading pressure, opposing/reinforcing displayed liquidity, depth, price reaction and confidence. **Do not promote the frozen linear impact model into live trading or use it as a universal simulator calibration.** The next calibration experiment should specify bounded response/dynamic-depth hypotheses before evaluating them on new contiguous same-venue days. A simulator should reproduce joint reaction distributions and transition behavior, with explicit anonymous-role assumptions; this comparison does not complete that simulator.

No live policy, real-money trading or cross-venue transfer was enabled. The earlier [full ecology study](ECOLOGY_PRICE_MECHANICS.md) contains the definitions, primary research sources and foundational limitations. Full distributions and diagnostics are saved per hour in [mechanics_replication](mechanics_replication).

## Reproduce

```bash
python -m src.simulation.csv_book_to_parquet <original-09-book.csv> <books-dir>/BTCUSDT_orderbook_2026-05-26_09.parquet
python -m src.simulation.book_changes <original-03-book.parquet> <books-dir>/BTCUSDT_orderbook_2026-05-26_09.parquet --out data/processed/mechanics_replication_states
python -m src.simulation.ecology_mechanics_replication --baseline docs/price_mechanics/summary.json --books-dir <books-dir> --trades-dir <trade-originals> --states-dir data/processed/mechanics_replication_states --out data/processed/mechanics_replication
python tools/report_mechanics_replication.py --source data/processed/mechanics_replication/report.json --out docs/mechanics_replication
python -m unittest discover -s tests -p 'test_simulation*.py'
```

Place the original 03:00 Parquet in books-dir as well as the converted 09:00 file. CSV conversion requires pyarrow; analysis also requires numpy and zstandard. Source bytes are not redistributed. Tests additionally verify one-nanosecond timestamp precision, integral decimal IDs, rejection of fractional IDs and altered-baseline rejection.
''')
    (out.parent/'ECOLOGY_MECHANICS_REPLICATION.md').write_text('\n'.join(lines)+'\n')


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--source',required=True);p.add_argument('--out',required=True);a=p.parse_args();render(a.source,a.out)
