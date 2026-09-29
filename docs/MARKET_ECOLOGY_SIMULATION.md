# Market Ecology simulation laboratory (experimental)

This module is isolated from frozen EXP-01, DBR, D06–D09 and Paper Engine definitions. It is a mechanistic counterfactual, not a calibrated market forecast or a trading signal.

## Run

From the repository root, with Python 3.13:

```bash
python -m src.simulation.ecology --config configs/simulation_v1_demo.json --out data/processed/simulation_v1
python -m src.simulation.ecology --config configs/simulation_v1_demo.json --rates configs/simulation_v1_flow_rates.json --out data/processed/simulation_v1_stateful
python -m unittest discover -s tests -p test_simulation_ecology.py
```

The first command needs only Python's standard library and writes a CSV time series plus JSON report to a gitignored output directory. To estimate the basic initial scales from other valid one-second ecology CSVs, install pandas and use `--input file1.csv file2.csv` instead of `--config`. Those CSVs require columns `mid`, `bid_top_qty`, `ask_top_qty`, `bid_depth_10bps`, `ask_depth_10bps`, `trade_count`, and `total_aggressive_qty`.

The second command uses a fitted, book-state-dependent background trade-count model. To regenerate its JSON from the two local prototype ecology CSVs, run `python -m src.simulation.flow_rates --train HOUR_00_ECOLOGY.csv --holdout HOUR_04_ECOLOGY.csv --out configs/simulation_v1_flow_rates.json`. The inputs require `top_obi`, two 10 bps depth columns and aggressive buy/sell trade counts. The training hour supplies depth tercile cutoffs and nine states: three OBI bins (below -0.25, middle, above 0.25) crossed with three total-depth bins. Within each state and side, a 30-second global-rate prior gives `lambda=(state_count + 30*global_rate)/(state_seconds + 30)`. This is a Gamma–Poisson posterior mean with fixed shrinkage; the Poisson likelihood is a count-model benchmark, not proof that counts are Poisson distributed.

The 00 UTC training hour has 1,331 valid book seconds. On the separate 04 UTC hour (703 valid seconds), buy/sell combined Poisson negative log likelihood per second was 34.19 for state-conditional rates versus 37.15 for a constant-rate baseline. That is a one-hour, same-day diagnostic. It does not establish stationarity, forecasting value, or independent-day replication. The fitted rates capture **aggressive trade counts only**; maker cancellation and replenishment remain assumed. In stateful mode, each paired run receives the same underlying uniform draws, while different book states can produce different arrival counts.

## Mechanism

Two makers each own half the initial bid and ask quantities at 770 price levels per side, tick size $0.10. Background liquidity takers arrive by a Poisson count with symmetric buy/sell directions and exponential sizes. A scheduled 80 BTC aggressive buy order arrives at second 120. In the paired scenario, maker B withdraws all quotes at that second and does not replenish for 60 seconds. The same random background flow is fed into both runs. Orders execute by price priority, with maker shares filled pro rata at a common price; time priority, latency, fees, hedging and fundamental-value movement are absent.

At price p, maker j's displayed quantity follows assumed fractional cancellation and deficit replenishment:

`cancelled[j,p,t] = 0.002 * Q[j,p,t]`

`posted[j,p,t] = 0.08 * max(target[j,p] / 2 - Q[j,p,t], 0)`

The demo config anchors initial mid, top quantities, approximate visible depth within 10 bps, median active trade count, and mean fill size to the two supplied BTCUSDT Futures sample hours (2026-05-25 00 and 04 UTC, 2,034 valid book seconds). The 770-level depth shape, Poisson arrivals, cancel/replenish rates, fixed reference price, 80 BTC order and withdrawal behavior are assumptions. Do not treat maker mark-to-mid accounting as profit.

The seed-7 paired run fills 80 BTC in each scenario. Its VWAP slippage relative to the pre-shock ask is about 2.03 bps with both makers and 4.40 bps after one withdraws. Ask depth at 10 seconds is about 140.6 versus 53.0 BTC. These are outputs of the assumed model, not observations of actual BTC market impact. More contiguous days are needed to estimate conditional arrival/depletion intensities and validate simulated spread, depth, price and recovery distributions on held-out periods. Level reductions in the observed L2 tape do not by themselves identify cancellations.

The model is inspired by the exchange/agent architecture of [ABIDES](https://github.com/abides-sim/abides) and the state-dependent queue perspective of [Huang, Lehalle and Rosenbaum](https://arxiv.org/abs/1312.0563). It does not reuse ABIDES code or claim to implement the full queue-reactive model.
