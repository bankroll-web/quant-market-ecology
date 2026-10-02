# Market Ecology simulation laboratory (experimental)

This module is isolated from frozen EXP-01, DBR, D06–D09 and Paper Engine definitions. It is a mechanistic counterfactual, not a calibrated market forecast or trading signal.

## Measured ecology and price reactions — October 2026

[Observed market ecology and price reactions](ECOLOGY_PRICE_MECHANICS.md) contains the six-recording statistical study, source/timing audit, conditional price distributions, frozen explanatory regressions, freshness checks and figure. It excludes windows with missing trade payloads or intersecting trade-ID gaps. Earlier strategy studies did not apply these stricter trade exclusions. Same-window explanations are not validated trading signals. The current free live observer uses Coinbase; historical BTCUSDT calibration is not automatically transferable to that venue.

[Frozen replication on two additional periods](ECOLOGY_MECHANICS_REPLICATION.md) applies the original settings to the saved 26 May 03:00 and 09:00 books and trades. The liquidity-reinforcement contrast repeats, while extreme imbalance/depth ratios expose a severe frozen linear-calibration failure at 03:00. These are additional hours from the same archive, not new days or certified untouched final tests.

[Robust response comparison](ROBUST_ECOLOGY_RESPONSE.md) separately tests fixed training-only clipping, asinh compression and time-weighted depth against that original calibration. [End goal and remaining development](MARKET_ECOLOGY_ROADMAP.md) states the data, simulator, policy, execution and live-shadow acceptance stages.

## Run the observer

From the repository root, with Python 3.13:

```bash
python -m src.simulation.ecology --config configs/simulation_v1_demo.json --out data/processed/simulation_v1
python -m src.simulation.observer --csv data/processed/simulation_v1/simulated_ecology.csv --out data/processed/simulation_v1/observer.html
python -m unittest discover -s tests -p test_simulation_ecology.py
```

Open `observer.html` locally. Move the second slider to compare maker A/B postings and displayed reductions, maker inventories, background buy/sell trades, spread, depth and midprice. This is 300 simulated seconds, not a full-day market replay. Outputs are gitignored.

## Mechanism and mathematical boundary

Two providers own half of 770 price levels per side at $0.10 ticks. Background takers arrive with an assumed constant Poisson rate, symmetric side and exponential fill sizes. An 80 BTC aggressive buy arrives at second 120. In the paired scenario maker B removes its quotes and pauses posting for 60 seconds. Both runs use the same background random draws. Execution respects price priority, with pro-rata maker allocation at each price; no latency, time priority, fees, hedging or fundamental-value process.

Assumed maker behavior at price p:

`displayed_reduction[j,p,t] = 0.002 * Q[j,p,t]` per second;

`posting[j,p,t] = 0.08 * max(target[j,p] / 2 - Q[j,p,t], 0)` per second.

These are **scenario parameters**, not inferred maker cancellation/replenishment rates. Mark-to-mid accounting is not profit. A prior prototype's one-second book reconstruction used looser event grouping; its fitted trade-count rate table was withdrawn. This branch uses a D06-audit-matching replay for the sample-derived initial book scale. The demo config contains exposure-weighted medians from 1,781.56 verified within-episode seconds across the uploaded 00 and 04 UTC files. Mean trade size uses all 201,967 matching raw trade rows; background trade frequency remains an assumed robust scale.

## Observed near-touch book changes

Install `pyarrow` and `zstandard` to process raw outer-Zstandard Parquet. Use the canonical-compatible *separate simulation diagnostic*:

```bash
python -m src.simulation.book_changes BTCUSDT_orderbook_2026-05-25_00.parquet BTCUSDT_orderbook_2026-05-25_04.parquet --out data/processed/book_changes
python -m src.simulation.book_change_rates --train data/processed/book_changes/BTCUSDT_orderbook_2026-05-25_00_observed_changes.csv --holdout data/processed/book_changes/BTCUSDT_orderbook_2026-05-25_04_observed_changes.csv --out data/processed/book_changes/rates.json
```

The replay matched frozen D06 audit counters for these two uploaded files: 00 UTC had 340 valid bridges, 24 invalid bridges, 918 stale updates and 42,839 valid states; 04 UTC had 122, 13, 307 and 23,749 respectively. It measures increases/decreases in displayed quantity at levels within 10 bps of the **pre-update** mid, only within verified episodes. Exposure is elapsed local receipt time between consecutive valid updates, not the span of an invalid gap. A reduction can be execution, cancellation, modification, or another cause; individual market makers are anonymous.

The diagnostic model crosses three top-OBI bands with exposure-weighted depth terciles. Four observed level-change counts (bid/ask increase/decrease) receive a Gamma–Poisson shrinkage estimate, `lambda=(state_count + 30*global_rate)/(state_exposure_seconds + 30)`. Training uses 1,145.40 verified exposure seconds in 00 UTC; holdout is 636.15 seconds in 04 UTC. On the prespecified same-day holdout, conditional Poisson negative log likelihood was **935.11 per exposure second**, worse than the constant-rate baseline **908.65**. The state table is retained as a diagnostic, **not used to drive simulated makers**. No additional bins or thresholds were selected against the holdout. Poisson is a count-likelihood benchmark, not an established arrival law.

A defensible maker-side simulator needs more contiguous days, a model of event sizes and timing, explicit treatment of executions when interpreting level reductions, and held-out distributional checks for spread, depth, impact and recovery. The observed tape cannot identify private participant roles.

## Research basis

The small exchange/agent design is inspired by [ABIDES](https://github.com/abides-sim/abides) and the state-dependent queue viewpoint of [Huang, Lehalle and Rosenbaum](https://arxiv.org/abs/1312.0563). This code does not reuse ABIDES or implement the full queue-reactive model.


## Live simulation laboratory

[Live ecology laboratory and mathematics](LIVE_ECOLOGY_LAB.md) connects fresh observations to frozen-book interventions and synthetic participant rollouts. Open `/ecology.html` on the deployed observer. Scenario assumptions and learned-policy limitations are shown in the dashboard.

## Cost-aware strategy research

The first [strategy comparison](STRATEGY_RESEARCH.md) tests linear and nonlinear regression against flow-sign and no-trade benchmarks using delayed bid/ask paper proxies. No candidate qualifies: no-trade wins validation. See [audited results](STRATEGY_RESEARCH_RESULTS.json) for costs, missing exits, input hashes and qualification limits. The Kraken collector now records public trade updates alongside the live book; free-instance recordings remain ephemeral.
