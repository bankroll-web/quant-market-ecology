# Joint trade and book event audit

The next integration layer reconstructs the valid training book and joins trades by receipt interval, passive side and exact price. Absolute L2 quantities remain authoritative. Trades annotate the observed book; they are not subtracted from it again. This prevents the naive replay error of counting executions twice.

## Training results

All 897 frozen accepted windows reconcile with the original near-touch additions, reductions and absolute executed trade quantities. Interval coverage, episode continuity and missing-data boundaries are checked. Source hashes and per-window results are retained in the [JSON](ECOLOGY_JOINT_EVENT_AUDIT_RESULTS.json).

| Measurement across accepted windows | BTC quantity |
|---|---:|
| Recorded executed trade quantity | 456.055 |
| Repeated gross near-touch displayed reductions | 187,297.527 |
| Candidate execution allocation | 339.607 |
| Trade quantity outside candidate allocation | 116.448 |
| Displayed reduction unexplained by this allocation | 186,957.920 |

About 74.5% of recorded trade quantity enters the candidate allocation under the stated receipt-order rule. This is **not** a validated execution-attribution rate. Gross reductions count repeated changes and can exceed starting depth many times. They are not unique withdrawn capital. Unexplained reductions do not establish cancellation volume or participant intent. These large gross quantities also require continuing source/bundle interpretation checks before event-rate calibration.

## Explicit allocation rule

For each valid consecutive book-receipt interval:

1. Take trades received strictly after the previous update and strictly before the current update.
2. Match their price and passive side: aggressive buys consume asks; aggressive sells consume bids.
3. At each price, cap the candidate allocation at the smaller of the observed net reduction and candidate trade quantity.
4. Retain unmatched trade quantity and unexplained displayed reduction separately.

Trades tied with the current book receipt are counted but excluded from attribution; ordering across feeds is unknown. No such ties occur inside these accepted training windows. Trades enter one interval only. Snapshot bridges and sequence failures reset the state; accepted windows must have exact uninterrupted coverage.

This is a bookkeeping scenario, not an identified execution decomposition or a proven bound. Absolute bundled updates hide simultaneous additions and removals. A cancellation can coincide with a trade at the same price. Trade and book feeds can arrive in different orders. Executions can be replenished before the update or occur outside retained book coverage.

## What this changes

The project now has a tested joint-event audit and a safe separation between authoritative book replay and candidate trade attribution. The generative maker simulator remains unchanged. Historical event replay can reproduce observed quantities; that does not show a model can generate realistic responses to new agent actions.

Next: expose asymmetric empirical liquidity paths in a separately labelled replay environment, retaining price-level placement and receipt timing. Then compare a generative maker model against that benchmark. Do not use completed-window response labels as pre-trade information or call a residual a cancellation without additional assumptions.

## Reproduce

```python
from src.simulation.ecology_joint_event_audit import audit

audit('/path/to/BTCUSDT_orderbook_2026-05-25_00.parquet',
      '/path/to/BTCUSDT_trades_2026-05-25_00.parquet',
      'data/processed/ecology_price_mechanics/2026-05-25_00_windows.csv',
      'docs/ECOLOGY_REGIME_DYNAMICS_RESULTS.json',
      'docs/ECOLOGY_JOINT_EVENT_AUDIT_RESULTS.json')
```

Requires numpy, pyarrow and zstandard. Use the complete original book file. This module permits only the frozen training hour, checks its accepted-window hash, and does not fit later periods. No new live policy or profitability claim is introduced.
