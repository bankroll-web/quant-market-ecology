# Historical Bitcoin trade-flow test

Status: research only; no tradable edge established, no live promotion, no orders.

## Data and fixed recipe

Verified public Binance BTCUSDT spot minute aggregates for June-August 2024: 132,480 contiguous minutes, 92 days, three matching SHA-256 archive checksums. The old July bars file was absent; these are freshly retrieved archives, not recovered original project bars. September 2026 archive URL returned 404.

Minute aggregates include taker-buy volume and trade count. Features use buying pressure, activity and mean trade size at 1/5/15/60-minute scales. No candle shapes, technical indicators, order-book liquidity, inferred identities or derivatives features. Tokenization here is 16-bin trade-flow summary tokenization, not the event tokenizer or a transformer.

June-July training; August 1-14 validation; August 15-31 evaluation. Purge unresolved labels across boundaries. Hourly decisions avoid overlapping positions even at 60 minutes. Feature minute finishes before entry; entry proxy is the open two minutes after that minute starts (one complete minute delay after its end). Exit uses the later minute open.

Recipe saved locally in SPEC.json before fitting. It was not externally registered before execution. Later dates are new to this recipe but prior project daily research may have inspected them: do not call them a globally untouched sealed test. Twelve classifier/regressor fits, 18 policy candidates; no post-evaluation tuning. These counts exclude earlier project experiments. Numeric and token models receive identical information; bin edges fit training only.

## Results

| Horizon | Constant direction log loss | Numeric | Tokens |
|---|---:|---:|---:|
| 5 min | 0.7005 | 0.7111 | 0.7315 |
| 15 min | 0.6964 | 0.6982 | 0.7032 |
| 60 min | 0.6929 | 0.7118 | 0.7044 |

Lower log loss is better. All six models also lost to the training mean-return baseline on return MSE. This recipe did not demonstrate better direction probabilities or move-size forecasts.

Validation selected the 15-minute token model with a predicted return above 20 bps: only two validation trades. It produced one evaluation trade across 17 days. Its actual gross log return was 19.2851 bps; after assumed 6 bps total friction it was 13.2851 bps, or 0.13285% on the trade notional under the additive bps convention. At 12 bps friction it was 7.2851 bps; at 20 bps it was -0.7149 bps. These are scenario deductions, not verified fills or actual venue fees.

The primary daily mean was 0.7815 bps across 17 days, with a day-bootstrap 95% interval [0, 2.3444]. One positive day and 16 flat days. The lower bound is not above zero; resampling one trade cannot establish robustness. The selection rule lacked a minimum-trade criterion, so it selected an extremely sparse policy. This weakness is disclosed rather than repaired using evaluation results. No strategy is qualified.

## Reproduce

Download the three public URLs in RESULTS.json and their .CHECKSUM files into data/raw/long_horizon. Install requirements-receipt-benchmark.txt. From repository root:

```sh
python long_horizon_flow.py
python -m unittest discover -s tests -p test_long_horizon_flow.py
```

Three tests passed: feature prefix invariance, training-only bin edges, and cost deduction including flat days. Input coverage and archive hashes are checked by the runner. Predictions and full metrics are saved alongside this report.

## Practical limits and next decision

Historical aggregation has no local receipt timestamps or execution book. Delayed open fills are proxies; costs are assumptions. Position sizing, available capital, capacity, spreads and latency distributions are not modelled. No short selling or funding is assumed. The 2024 spot study cannot be promoted directly to the Kraken live learner or Binance futures.

Reject this recipe as a demonstrated edge. Before a new independent-period test, strengthen the selection protocol with a minimum effective sample requirement and test economically motivated interactions on separate development periods. Retain numeric baselines and event-level token research. More model size alone is not supported by these results.
