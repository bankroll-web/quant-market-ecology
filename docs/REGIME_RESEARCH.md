# Quantitative horizon and liquidity-regime analysis

> Replay integrity correction: the 25 May 18 UTC local tape used for these historical numbers was a truncated prefix. See [the correction and rebuilt analysis](OBSERVED_MARKET_MECHANICS.md#replay-integrity-correction). These numbers are preserved for provenance and must not be treated as a completed whole-hour evaluation.


**Result: no candidate qualifies.** The expanded analysis compares 260 fixed candidate/configuration combinations and selects no trading under the stated cost and missing-exit stress assumptions. This is development research on previously inspected data; it is not an independent final test.

## Mathematical question

Can completed flow, current imbalance and current liquidity predict a subsequent move large enough to survive execution costs? We test one-, five-, fifteen-, thirty- and sixty-second holding periods, with entry delays of 100 and 500 ms. Decisions use receipt-time post-update states and completed flow only. Parameters and transformations are fitted on 25 May 12 UTC; selection uses 25 May 18 UTC; later checks use 26 May 15 and 21 UTC.

For each horizon/delay, compare 24 deterministic rules, linear ridge and nonlinear RBF kernel ridge, plus a no-trade benchmark. The rules combine follow/reverse-flow and follow/reverse-imbalance directions with six eligibility gates: all observations, high flow, high imbalance, thin liquidity, deep liquidity, and flow/imbalance agreement. High flow and imbalance use training-only 75th percentiles; thin/deep liquidity use training-only 25th/75th percentiles of log depth. Quantiles use resolved training labels and therefore inherit possible missing-label selection bias.

Kernel ridge uses `K(i,j)=exp(-||z_i-z_j||²/6)` and alpha=1; ridge uses alpha=1. Both standardize using training data only. Learned signals require absolute predicted midpoint response greater than the assumed round-trip cost plus the current spread. This does not forecast the future spread or actual fills.

Quote-based long return is `10000*(exit_bid/entry_ask-1)`; short return is `10000*(entry_bid-exit_ask)/entry_bid`. Subtract assumed fees/slippage of 5 or 10 bps per round trip, beyond observed quote crossing. Five bps equals 0.05% of entry notional. Actual account fees remain unspecified. Returns are equal-unit small-order proxies, not portfolio cash performance.

## Missing exits and dependence

Endpoint quotes must be in the decision's verified episode and within 250 ms of the scheduled entry/exit target. Future availability never controls the feature vector or the decision schedule. Each attempted decision reserves its entire horizon plus endpoint tolerance, including unresolved entries/exits. Models are evaluated separately on resolved rows and on rows where an entry is observable but the exit is missing.

For unresolved opened positions, report hypothetical additional losses of 10 and 50 bps each. These are sensitivity scenarios, not measured losses or guaranteed worst-case bounds. They cannot reconstruct an actual position after a gap. Candidate selection uses the validation sum under the 50-bps scenario, requires at least five resolved validation trades, and defaults to no-trade if nonpositive. Equal-unit sums across different horizon coverage are only exploratory rankings.

One-minute block bootstrap intervals resample within-hour block sums and opportunity counts jointly, retaining zero-trade observations. They preserve within-block dependence but do not establish independence across blocks, handle gaps or between-day regime uncertainty. Fewer than ten observed blocks returns no interval. Intervals are not adjusted for the 260 comparisons and cannot certify profitability. The selected no-trade policy's zero interval means abstention, not successful alpha estimation.

## What the data says

At 100 ms entry delay, the validation hour contains:

| Scheduled horizon | Resolved opportunities | Opportunities where perfect future direction beats 5 bps costs | Missing exits |
|---|---:|---:|---:|
| 1 second | 161 | 0 | 8 |
| 5 seconds | 65 | 0 | 16 |
| 15 seconds | 27 | 0 | 9 |
| 30 seconds | 11 | 0 | 9 |
| 60 seconds | 4 | 0 | 8 |

The perfect-direction diagnostic knows future bid/ask quotes and chooses the more profitable direction or abstention at each resolved opportunity. It is **not tradable**. In these particular sampled validation opportunities, even that optimistic diagnostic cannot clear the assumed five-bps cost. This finding applies to the sampled fixed-time entry/exit proxies; it is not a statement that no trade, venue or strategy can make money.

All ten horizon/delay configurations select no-trade. The same conclusion holds before the missing-exit penalty for candidates with at least five resolved validation trades: none has a positive aggregate resolved validation result at the assumed five-bps cost.

A useful example of a misleading isolated result is the 30-second, 100-ms flow-follow rule restricted to flow/imbalance agreement. It has +16.83 summed bps on 10 resolved opportunities in 26 May 15 UTC, but -69.31 summed bps on 15 opportunities in the later 21 UTC hour. The earlier positive hour also has 21 unresolved opened positions. It already loses validation and is not selected. Looking only at its profitable hour would create an unsupported conclusion. These sums are not compounded account returns.

The sixty-second validation horizon resolves only four observations. Longer holding times expose the existing coverage problem rather than establish a richer validated edge. Gaps can preferentially remove volatile price transitions, so stable resolved prices must not be generalized to the whole hour.

## Development decision

Do not activate these candidates in the live system. The current evidence indicates that the observed short-horizon signals and assumed execution economics are insufficient in this sample. Trying more algorithms on the same four inspected hours would increase adaptive selection risk without supplying independent evidence.

The next useful research branches are:

1. Durable contiguous paired book/trade collection on one selected venue, with audits of capture delay, gaps and trade IDs. The existing free Render recorder remains ephemeral, so it cannot yet certify a multi-day archive.
2. Actual fee/order-size/latency calibration. Lower fees, passive execution and other venues must be evaluated as distinct hypotheses; do not merely lower costs to manufacture a profitable result.
3. Longer-horizon features from continuous coverage and multiple days. Preserve later days untouched until strategy selection ends.
4. For passive market making, calibrate fills, inventory risk and adverse selection from observed events. An L2 midpoint response cannot prove maker profitability or queue fills. Use the supplied market-making papers for policy/control structure after their required data and assumptions are available.

There is no measured dealer inventory, retail/institution identity or option-chain GEX in this dataset. Options, auctions and macro branches require their corresponding data and cannot supply missing evidence by assumption. Historical Binance futures experiments remain separate from the live Kraken spot feed.

## Reproduce and inspect

```bash
python -m src.simulation.regime_research --flow-dir data/processed/decision_response --book-dir data/processed/replay_states --out data/processed/regime_research
python -m unittest discover -s tests -p 'test_simulation*.py'
```

Requires NumPy. The full reproducible run writes all candidate/hour scores to `report.json`. The [committed summary](REGIME_RESEARCH_RESULTS.json) records input hashes and links ten configuration snapshots. Each snapshot includes all validation candidate scores, audit counts, training thresholds, oracle diagnostics, selected-policy intervals and all-hour scores for the best resolved-validation diagnostic rule. The omitted all-hour scores for other rejected rules can be regenerated; they are not used to change validation selection.

The previous [first comparison](STRATEGY_RESEARCH.md) remains a benchmark. The [timing audit](TIMING_AND_OBSERVATION_AUDIT.md) explains why the four hours are neither full days nor pristine final evaluation. Fifty simulation software tests pass; this does not establish financial performance.
