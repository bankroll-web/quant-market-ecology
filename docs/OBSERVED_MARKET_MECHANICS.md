# Observed market mechanics and ecology calibration

This stage returns to the ecology foundation: measure how aggressive flow, displayed liquidity and price move together before attempting to promote a strategy. It does not identify hidden participants or infer their psychology.

## New live panel

The Kraken BTC/USD laboratory shows a rolling ten-second receipt-time window:

- Taker buy and sell BTC from public trade updates; buy/sell describes the aggressor side.
- Bid/ask displayed quantities added and reduced within ten basis points of the pre-update midpoint, limited to the subscribed book.
- Addition/reduction ratios separately for each side. A missing denominator produces no ratio.
- Observed midpoint movement between the first and last book observations remaining in that window.

A ratio `R = added BTC / reduced BTC` above one means more additions than reductions were observed in that receipt window; it is not proof of maker replenishment or a directional forecast. Trade imbalance is `(buy BTC - sell BTC)/(buy BTC + sell BTC)` when total flow is nonzero. Price movement is `10000*(last midpoint/first midpoint - 1)`.

A buyer burst together with rising asks, stable price and ask-side additions is a possible absorption pattern worth testing. The panel measures the co-occurrence; it cannot establish that those additions caused stability, that the same participants supplied them, or that a named institution traded. Cancellations and executions both reduce L2 quantities. Do not subtract trade flow from reductions and call the remainder cancellations: feeds can be delayed and aggregated differently.

Snapshots initialize the book but are not counted as newly added liquidity. Failed CRC32 updates clear all rolling observations. Reconnects reset the window. Trade IDs are deduplicated in a bounded in-memory set for mechanics metrics; raw capture still retains received messages. Invalid trade quantities/IDs/sides mark the rolling window incomplete. The bounded event buffer also marks incomplete windows when capacity was exceeded. Trade counters elsewhere in the UI remain received-event counts, not deduplicated totals.

The status becomes observed after ten seconds of local accumulation with a usable book and active trade subscription. This is not certification of exchange event completeness or clock synchronization. An active subscription cannot prove a quiet trade channel has delivered every trade. Metrics use receipt times, not fitted exchange-causal alignment. Buffer truncation, subscribed depth and reconnect gaps remain limitations. Stale/invalid book observations hide the panel.

## Historical calibration

`ecology_calibration.py` fits nine states defined by pre-update top imbalance and training exposure-weighted depth terciles. It estimates displayed level-add/reduction counts per second and corresponding changed BTC per second. Training is 25 May 12 UTC; later previously inspected hours are evaluation diagnostics. Thirty seconds of prior exposure shrink state estimates toward global rates:

`state rate = (state observed quantity + 30 * global quantity rate) / (state exposure seconds + 30)`.

Count evaluation compares state-conditional and constant Poisson diagnostic likelihoods. Updates bundle level changes and can be overdispersed; this is not a validated arrival law or a fitted Hawkes process. Quantity evaluation compares aggregate observed and expected BTC per second. None of these rates identifies actual maker/cancel orders, FIFO queue positions, inventory or psychological states.

The model parameters are saved for research comparison, not automatically wired into synthetic makers. Historical Binance futures calibration must be tested on separately captured Kraken data before any cross-product transfer. [Calibration results](ECOLOGY_CALIBRATION_RESULTS.json).

## Replay integrity correction

During calibration, a local 25 May 18 UTC post-update replay was found to end inside a CSV row. Its 20,411 complete rows covered only a prefix of the hour. The original recording was rebuilt to 57,366 complete within-episode intervals and approximately 1,565.25 seconds of verified exposure. This still does not provide a continuous full hour.

Earlier strategy, regime and timing reports used the prefix tape and flow windows derived from it. Their 18 UTC validation numbers must be treated as superseded limited-prefix diagnostics, not whole-hour results. Other input tapes were kept unchanged. Old snapshots are preserved for provenance; repaired runs are stored separately. New research loaders reject structurally incomplete rows. A well-formed row alone cannot establish full coverage: source hashes, completed replay counters and verified exposure must also be checked.

## Next foundation work

Durable recordings remain necessary: the free Render instance's files disappear on restart. After archiving contiguous book/trade periods, audit coverage and timestamps, calibrate joint arrival/replenishment behavior, and compare simulated spread, depth, return and inventory distributions with later observations. Psychological explanations should be competing scenario hypotheses tested against observable consequences, not hidden-state facts inferred from anonymous L2.

Measured option gamma requires an option chain, volatility surface and signed-position assumptions. Macro bubble and auction branches require their own datasets. Profitability remains a later and separate execution-aware qualification test.

## Reproduce

```bash
python -m src.simulation.book_changes RAW_18_HOUR_BOOK --out data/processed/replay_repaired
# Add the other completed, audited hour tapes to that folder.
python -m src.simulation.decision_response --raw-dir RAW_FOLDER --states-dir data/processed/replay_repaired --out data/processed/decision_repaired
python -m src.simulation.ecology_calibration --book-dir data/processed/replay_repaired --out docs/ECOLOGY_CALIBRATION_RESULTS.json
python -m unittest discover -s tests -p 'test_simulation*.py'
```

Book rebuilding requires pyarrow/zstandard. The live mechanics module uses the standard library. Related: [laboratory](LIVE_ECOLOGY_LAB.md), [paper integration](LEARNING_MODEL_INTEGRATION.md).

## Repaired research result

Rebuilding the 18 UTC tape increases resolved five-second validation opportunities from 65 to 193. Re-running the first cost-aware comparison and all 260 horizon/regime candidates still selects no trading. These repaired results supersede the prefix-based selection diagnostics; they do not establish independent validation. [First comparison](STRATEGY_REPAIRED_RESULTS.json), [regime selection summaries](REGIME_REPAIRED_RESULTS.json), [rebuild counters](REPLAY_18_REPAIR_AUDIT.json). Full per-candidate scores remain reproducible with the repaired tape and flow directories.

The historical state-conditional level-change diagnostic improves versus the constant model by 1.26% at 25 May 18 UTC and 4.22% at 26 May 15 UTC, but worsens by 2.94% at 26 May 21 UTC. These are likelihood diagnostics, not price-forecast accuracy or profitability percentages. Fifty-five simulation tests pass, including rolling-window boundaries, deduplication, reset after CRC32 failure, incomplete-row rejection and training-only quantity calibration.
