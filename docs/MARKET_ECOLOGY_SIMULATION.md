# Market Ecology simulation laboratory (experimental)

This module is isolated from frozen EXP-01, DBR, D06–D09 and Paper Engine definitions. It is a mechanistic counterfactual, not a calibrated market forecast or a trading signal.

## Run

From the repository root, with Python 3.13:

```bash
python -m src.simulation.ecology --config configs/simulation_v1_demo.json --out data/processed/simulation_v1
python -m unittest discover -s tests -p test_simulation_ecology.py
```

The first command needs only Python's standard library and writes a CSV time series plus JSON report to a gitignored output directory. To estimate the basic initial scales from other valid one-second ecology CSVs, install pandas and use `--input file1.csv file2.csv` instead of `--config`. Those CSVs require columns `mid`, `bid_top_qty`, `ask_top_qty`, `bid_depth_10bps`, `ask_depth_10bps`, `trade_count`, and `total_aggressive_qty`.

## Mechanism

Two makers each own half the initial bid and ask quantities at 770 price levels per side, tick size $0.10. Background liquidity takers arrive by a Poisson count with symmetric buy/sell directions and exponential sizes. A scheduled 80 BTC aggressive buy order arrives at second 120. In the paired scenario, maker B withdraws all quotes at that second and does not replenish for 60 seconds. The same random background flow is fed into both runs. Orders execute by price priority, with maker shares filled pro rata at a common price; time priority, latency, fees, hedging and fundamental-value movement are absent.

At price p, maker j's displayed quantity follows assumed fractional cancellation and deficit replenishment:

`cancelled[j,p,t] = 0.002 * Q[j,p,t]`

`posted[j,p,t] = 0.08 * max(target[j,p] / 2 - Q[j,p,t], 0)`

The demo config anchors initial mid, top quantities, approximate visible depth within 10 bps, median active trade count, and mean fill size to the two supplied BTCUSDT Futures sample hours (2026-05-25 00 and 04 UTC, 2,034 valid book seconds). The 770-level depth shape, Poisson arrivals, cancel/replenish rates, fixed reference price, 80 BTC order and withdrawal behavior are assumptions. Do not treat maker mark-to-mid accounting as profit.

The seed-7 paired run fills 80 BTC in each scenario. Its VWAP slippage relative to the pre-shock ask is about 2.03 bps with both makers and 4.40 bps after one withdraws. Ask depth at 10 seconds is about 140.6 versus 53.0 BTC. These are outputs of the assumed model, not observations of actual BTC market impact. More contiguous days are needed to estimate conditional arrival/depletion intensities and validate simulated spread, depth, price and recovery distributions on held-out periods. Level reductions in the observed L2 tape do not by themselves identify cancellations.

The model is inspired by the exchange/agent architecture of [ABIDES](https://github.com/abides-sim/abides) and the state-dependent queue perspective of [Huang, Lehalle and Rosenbaum](https://arxiv.org/abs/1312.0563). It does not reuse ABIDES code or claim to implement the full queue-reactive model.
