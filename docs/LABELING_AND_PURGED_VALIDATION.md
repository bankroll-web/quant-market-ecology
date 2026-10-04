# Receipt-clock labels and purged walk-forward validation

Implemented research utilities in market_label_validation.py. Not integrated into the live learner, no trained strategy or orders. Six focused tests pass.

## Triple barriers

Call triple_barrier with ordered received bid/ask quotes, a known decision time, deadline, positive profit/loss bps, latency, explicit roundtrip fee assumption, and continuity bound. Thresholds must be determined from information available at the decision (e.g. a past-only volatility estimate). Never use future realized volatility or the completed outcome to set barriers.

Entry is the first received quote at/after assumed latency, bounded in age. A long enters at ask and exits at bid; short reverses these. Top quotes are proxies, not guaranteed fills, executable depth or a queue model. Fees are an assumed log-bps deduction. Barrier monitoring begins on subsequent received quotes. Outcomes record first observed barrier crossing; unobserved moves between messages cannot be recovered. Prices jumping beyond a barrier use observed exit price, not perfect barrier fills.

Labels +1/-1/0 mean profit/loss/time barrier first. A time label is not zero return: net_log_bps preserves the realized exit proxy. Entry, outcome and label-availability times are separate. A time exit uses the last received state at/before deadline; later receipt coverage is required and sets label availability. Missing coverage, resets, invalid books and gaps censor observations instead of assigning neutral labels.

This utility deliberately does not infer which barrier came first from candle high/low. If both barriers lie inside one aggregate bar, ordering is unknown without finer data. Minute aggregate archives cannot be silently treated as received quote tapes.

## Purging

purged_walk_forward uses explicit information start/end intervals, removes training intervals overlapping any test interval inclusively, and restricts training to past rows. Set end to label_available_ns, including delayed coverage. Set start to the earlier causal feature-window start if shared feature history must also be excluded. Bins, scaling, feature selection and participant clusters must fit each training fold only.

Embargo extends exclusion after test intervals. In this past-only implementation future training rows are already excluded; do not claim that changing embargo alone repairs lookahead. Nested validation is still needed for model selection and meta-labeling.

## Scope of the proposed research

OFI from best-quote changes is distinct from the minute taker-volume fraction used in the recent historical experiment. The literature on short-horizon OFI does not establish hourly BTC predictability. HAR is primarily a volatility baseline, not a direction indicator. HMM regime probabilities must be filtered using past observations rather than smoothed over future data. Funding, open interest and liquidations require separately verified timestamped sources. No missing features are fabricated.

Triple barriers, purging and meta-labeling are methods, not a guarantee of correctness or profitability. Do not state that backtest/live discrepancies are usually leakage without investigating the actual feed, costs and timing. Deflated Sharpe requires a defensible trial registry and distribution assumptions; it is not calculated here. Meta-labels cannot be trained from in-sample primary predictions and claimed independent.

## Run tests

```sh
python -m unittest discover -s tests -p test_market_label_validation.py
```

Covered: first-hit ordering, spread/fees, missing coverage, reset censoring, latency/as-of exit and inclusive purging. Next integration needs an audited quote tape and fixed causal volatility/barrier settings, with the constant and numeric models retained as baselines.
