"""Render empirical regime continuity and frozen transition benchmarks."""
import argparse
import json
from pathlib import Path


def render(source,out):
    r=json.loads(Path(source).read_text());out=Path(out);out.parent.mkdir(parents=True,exist_ok=True)
    transitions=sum(x['summary']['eligible_transitions'] for x in r['results'].values())
    excluded=sum(x['summary']['excluded_boundaries'] for x in r['results'].values())
    lines=[f'''# Observed ecology regime dynamics

Completed 3 October 2026. This benchmark measures how the accepted observed liquidity/pressure labels follow one another. It adds empirical transition and persistence checks for future simulator validation; it does not establish a validated simulator or profitable policy.

## Definitions and continuity

The pressure cutoff is frozen from 25 May 00:00. Labels are no signed net flow, lower pressure, high pressure with reinforcing displayed liquidity, high pressure with opposing displayed liquidity, and high pressure with exactly neutral displayed pressure. No signed net flow may include trades that balance each other; it does not mean no trading activity. Reinforcement/opposition is relative to the current window's aggressive trade direction, so a state persisting does not imply persistent buying or selling.

A transition exists only if one accepted window ends exactly when the next accepted window starts and both are in the same reconstructed episode. Removing an invalid, missing-trade or stale window therefore breaks continuity. No transition crosses a recording boundary. Of the 8,300 accepted windows, **{transitions:,} adjacent transitions** qualify; **{excluded:,} within-recording adjacent boundaries** are excluded. These are selected discontinuous segments from the same inspected two-day archive.

| Period, UTC | Valid transitions | Excluded boundaries | Contiguous segments |
|---|---:|---:|---:|''']
    for h,x in r['results'].items():
        s=x['summary'];lines.append(f"| {h} | {s['eligible_transitions']} | {s['excluded_boundaries']} | {s['contiguous_segments']} |")
    lines.append('''
## Observed runs and censoring

A run ends at a change of label or an observation boundary. Runs touching the beginning or end of a contiguous segment are censored. Their observed lengths are not complete lifetimes. The table reports medians of observed run lengths including boundary-censored runs; it must not be interpreted as a population duration estimate or subsecond event timing.

| Period | Median lower-pressure run, observed seconds | Median high/reinforcing run | Median high/opposing run | Completed high/reinforcing runs |
|---|---:|---:|---:|---:|''')
    for h,x in r['results'].items():
        g=x['summary']['regimes'];lines.append(f"| {h} | {g['low_pressure']['median_observed_run_seconds']:.3f} | {g['high_reinforces']['median_observed_run_seconds']:.3f} | {g['high_opposes']['median_observed_run_seconds']:.3f} | {g['high_reinforces']['completed_runs']} |")
    lines.append('''
High-pressure labels generally have one-window observed median runs; lower-pressure runs are generally closer to two windows, except the busy 15:00 recording. This describes aggregate labels at approximately one-second resolution. It does not show that real pressure episodes last exactly one second, and repeated missing observations can shorten recorded runs.

## Frozen transition diagnostic

Two categorical benchmarks train only on valid adjacent transitions in 25 May 00:00:

* A first-order transition model conditions the next label on the previous label. Each transition cell receives a fixed 0.5 pseudocount.
* An IID model uses the marginal destination-label frequencies of those same training transitions, also with 0.5 pseudocounts. It ignores the previous label.

The conditional probability is P(j|i)=(Nij+0.5)/(sum_j Nij+5×0.5). This is a smoothed statistical benchmark, not proof that market states obey a Markov law. Neutral high pressure is never observed in these recordings; the smoothing nevertheless gives it prior probability. An unobserved source state's uniform row is entirely prior-generated and must not be represented as measured market behaviour.

Log loss is minus log2 of the assigned probability of the observed next label. Lower is better. Positive IID-minus-transition loss means the transition model is better. The paired intervals use 1,000 one-minute block-bootstrap draws, are exploratory and are not multiple-comparison adjusted.

| Period | Conditional log loss, bits | IID log loss, bits | IID minus conditional [95% interval] |
|---|---:|---:|---|''')
    for h,x in r['results'].items():
        s=x['scores'];d=s['iid_minus_markov_loss_bits'];lines.append(f"| {h} | {s['markov_log_loss_bits']:.4f} | {s['iid_log_loss_bits']:.4f} | {d['mean']:.5f} [{d['lower']:.5f}, {d['upper']:.5f}] |")
    lines.append('''
The conditional benchmark has lower point-estimate loss in only two of the seven comparison periods. Some intervals barely exclude zero and should not be elevated into strong discovery claims. There is no consistent advantage over the IID benchmark. The 15:00 distribution differs markedly from the training period, and both frozen benchmarks have much higher loss there. These results argue against treating a stationary first-order transition matrix as a validated event environment.

## Consequence for simulator development

A simulator can now be checked against the empirical transition counts, occupancy proportions, run-segment distributions, boundary-censoring rates and unchanged-price fractions. The benchmark keeps missing intervals from being mistaken for state persistence or transitions. It does not supply queue-event arrival intensities, participant identity, causal interventions, complete run-lifetime estimates or forward price alpha.

The conditional benchmark remains diagnostic. A richer semi-Markov, event-intensity or history-aware hypothesis would require a separate specification and evaluation, including additional contiguous same-venue days. Neither adding complexity nor replaying this archive creates independent validation. The live observer's synthetic participant roles remain assumptions.

Full transition counts, smoothed training probabilities, per-state run counts and freshness sensitivity: [ECOLOGY_REGIME_DYNAMICS_RESULTS.json](ECOLOGY_REGIME_DYNAMICS_RESULTS.json). Development gates: [MARKET_ECOLOGY_ROADMAP.md](MARKET_ECOLOGY_ROADMAP.md).

## Reproduce

```bash
python -m src.simulation.ecology_regime_dynamics --baseline docs/price_mechanics/summary.json --base-windows data/processed/ecology_price_mechanics --replication-windows data/processed/mechanics_replication --out data/processed/ecology_regime_dynamics
python tools/report_ecology_regime_dynamics.py --source data/processed/ecology_regime_dynamics/report.json --out docs/ECOLOGY_REGIME_DYNAMICS.md
python -m unittest discover -s tests -p 'test_simulation*.py'
```

Dependencies and accepted-window reconstruction are documented in the preceding ecology studies. Tests verify sign-relative labels, gap/episode boundaries, run censoring and smoothed-row normalization. No real-money or live-policy operation was enabled.
''')
    out.write_text('\n'.join(lines)+'\n')


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--source',required=True);p.add_argument('--out',required=True);a=p.parse_args();render(a.source,a.out)
