# Real-data timing and decision-boundary audit

> Replay integrity correction: the 25 May 18 UTC local tape used for these historical numbers was a truncated prefix. See [the correction and rebuilt analysis](OBSERVED_MARKET_MECHANICS.md#replay-integrity-correction). These numbers are preserved for provenance and must not be treated as a completed whole-hour evaluation.


Audit completed on the four available paired hours. It reads raw L2 update messages and raw trades, preserving their file order, and checks the emitted verified book-state intervals. This does not synchronize clocks or establish a trading signal.

## Raw timing

| UTC hour | Book update median age ms | Book update p95 age ms | Trade p95 age ms | Verified book exposure sec | Coverage of nominal hour |
| --- | ---: | ---: | ---: | ---: | ---: |
| 2026-05-25_12 | 116.6 | 396.2 | 560.8 | 1504.5 | 41.8% |
| 2026-05-25_18 | 117.4 | 358.9 | 354.7 | 555.9 | 15.4% |
| 2026-05-26_15 | 147.5 | 4192.2 | 2304.2 | 1369.7 | 38.0% |
| 2026-05-26_21 | 117.0 | 421.8 | 348.2 | 1923.7 | 53.4% |

All four files have zero backwards receipt timestamps, zero backwards exchange timestamps, zero negative measured ages, and zero duplicate trade IDs. Book updates can share a receipt timestamp; their level rows are collapsed into messages for timing statistics. Raw book timing includes invalid episodes; earlier studies measured valid emitted intervals only, so their quantiles need not match.

Receipt minus exchange timestamp includes clock offset, network delay, buffering and capture processing. It is not a measured exchange-execution latency. In the busy 26 May 15 UTC hour, 95% of book updates have age at most about 4.19 seconds and 95% of trades at most 2.30 seconds; the remaining 5% have greater ages. Substantial tails prevent interpreting receipt-time lead/lag as exchange causality.

Verified exposure is the sum of reconstructed within-episode consecutive-update intervals, divided here by the nominal 3600 seconds for a coverage indicator. Gaps are not carried forward. These files do not provide a continuously verified whole trading day.

## Observation boundary

For every comparable consecutive row within the same episode, the previous post-update midpoint exactly matches the next pre-update midpoint. Zero mismatches were found. Median adjacent emitted receipt intervals are about 26-28 ms in these hours. The old pre-update midpoint assigned to the current receipt time therefore describes the preceding state, rather than the newly available updated state. This is a state-timing convention issue, not proof that future prices leaked into the old feature.

The new `decision_response` command uses post-update midpoints at their receipt times. It rejects old book/trade messages only inside the completed flow window, whose contents are known by the decision at window end. It never uses future-label message ages to decide whether that decision was eligible. Forward labels still require a verified same-episode endpoint within 250 ms after the target, so missing-label selection remains a limitation for offline evaluation.

## Post-update response results

These are direction-aligned averages for completed windows with absolute signed flow at least 1 BTC. A positive value means movement in the direction of net aggressive flow. It is not a fitted prediction or a causal impact estimate.

| UTC hour | Eligible decisions | During-window mean bps | Next-1s labels | Next-1s mean bps | Next-5s labels | Next-5s mean bps |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| 2026-05-25_12 | 75 | 0.218 | 71 | 0.063 | 66 | 0.094 |
| 2026-05-25_18 | 24 | 0.176 | 22 | 0.035 | 21 | 0.160 |
| 2026-05-26_15 | 96 | 0.479 | 84 | 0.167 | 73 | -0.001 |
| 2026-05-26_21 | 66 | 0.217 | 63 | 0.032 | 58 | 0.037 |

Subsequent averages are small and unstable across hours/horizons. No confidence, significance, profitable-alpha or deployment claim is made. Labels can overlap; counts are not independent sample sizes. Decisions include all flow-window messages known at the origin, while a later delayed book label remains in the analysis. The 250-ms age threshold and 1-BTC flow cutoff remain exploratory. The new run is recorded against its exact input hashes; differences from previous documented samples are not interpreted as pure timing effects.

## Reproduce

From the repository root with NumPy, pyarrow and zstandard:

```bash
python -m src.simulation.timing_audit --raw-dir RAW_FOLDER --states-dir data/processed/replay_states --out data/processed/timing_audit.json
python -m src.simulation.decision_response --raw-dir RAW_FOLDER --states-dir data/processed/replay_states --out data/processed/decision_response
python -m unittest discover -s tests -p 'test_simulation*.py'
```

The states folder must contain the four post-update tapes from the historical replay. Raw folders must contain one book file per requested hour and its matching trade file; duplicate copies should be put outside this run folder. Timing module ignores snapshot rows when reporting update-message ages. [Raw audit results and hashes](TIMING_AUDIT_RESULTS.json); [post-update response snapshot](DECISION_RESPONSE_RESULTS.json). The original flow-response command keeps its pre-state and retrospective-filter defaults, preserving earlier research definitions.

## Readiness decision

**Ready:** continue engineering a read-only live observer with sequence/gap checks, receipt-time post-update features, explicit stale/gap flags, reconnect/resnapshot handling and captured events for replay. Historical audit completion is not proof that a live connector has been tested.

**Not ready:** calibrated arrival/queue learning on contiguous real days, exchange-causal price-impact claims, or automated trading. We need one complete paired day first, then additional later days held out from model selection, plus provider timestamp/sequence documentation. Live funding/fees/contract terms will be required before simulation economics can match the chosen venue.

Next implementation should build the read-only ingestion/observer boundary and test it with disconnect, duplicate and gap fixtures before a live connection. Do not silently shift timestamps by a fitted offset or carry invalid books through gaps.

Related: [historical replay](HISTORICAL_MARKET_REPLAY.md), [frozen regression](RESPONSE_REGRESSION.md), [learning integration](LEARNING_MODEL_INTEGRATION.md).
