# PE-3A — Observation Clock Audit (timestamp availability)

**Status:** AUDIT COMPLETE — STOP condition triggered (trade-side provenance missing from validated intermediates)
**Date:** 2026-09-13
**Scope:** PE-3A only. No latency grid, no execution model, no costs, no PnL.
**Inputs inspected:** raw CryptoHFT parquet (orderbook + trades, all 6 hours), frozen D06/D07/D08C/D09/D09B tapes, `src/book/replay.py`, `src/ingestion/cryptohft.py`, `src/liquidity/events.py`, `src/liquidity/joint_flow.py`, `src/liquidity/touch_ecology.py`, `src/paper_engine/events.py` / `state.py`.

---

## 1. Every relevant timestamp field available

### Raw validated inputs (gate0, CryptoHFT parquet)

| Layer | Field | Units | Meaning |
|---|---|---|---|
| Orderbook | `received_time` | ns epoch (int64) | Local collector receipt time of the book message |
| Orderbook | `event_time` | ms epoch (int64) | Exchange event time (Binance) |
| Orderbook | `transaction_time` | ms epoch (int64) | Exchange transaction time (Binance) |
| Trades | `received_time` | ns epoch (int64) | **Local collector receipt time of the trade message** |
| Trades | `event_time` | ms epoch (int64) | Exchange event time (equals `trade_time` in observed data) |
| Trades | `trade_time` | ms epoch (int64) | Exchange trade time (Binance) |

### Validated intermediates (frozen tapes)

| Layer | Field | Units | Meaning |
|---|---|---|---|
| D06 book states | `received_time`, `event_time` | ns / ms | passthrough from raw orderbook |
| D07 event tape | `received_time_ns` | ns epoch | local receipt of the book event |
| D07 event tape | `event_time_ms` | ms epoch | exchange event time |
| D07 event tape | `transaction_time_ms` | ms epoch | exchange transaction time |
| D07 event tape | `event_time_utc`, `transaction_time_utc` | UTC string | derived from ms |
| D08C alignment | `trade_time_ms`, `prev_book_time_ms`, `next_book_time_ms`, `nearest_book_time_ms`, `previous_lag_ms`, `next_lead_ms`, `nearest_distance_ms`, `trade_time_utc` | ms epoch / ms | exchange-time alignment of each trade to book events; **no receipt time** |
| D09 joint | `t0_event_time_ms`, `t1_event_time_ms`, `interval_ms`, `t0_utc`, `t1_utc` | ms epoch / ms | exchange event times of interval endpoints; **no receipt time** |
| D09B joint | same as D09 + `event_time_ms` (dup of t1) + touch-distance buckets | ms epoch | **no receipt time** |

## 2. Units

- `received_time` / `received_time_ns`: **nanoseconds** since epoch (int64).
- `event_time` / `event_time_ms`, `transaction_time` / `transaction_time_ms`, `trade_time` / `trade_time_ms`, all `*_book_time_ms`, `interval_ms`, lags/leads: **milliseconds** since epoch (int64).
- `*_utc` strings: derived from the ms fields (`pd.to_datetime(unit="ms", utc=True)`).

## 3. Semantic meaning

- **Exchange event time** (`event_time`): the time Binance assigned to the message (when the exchange generated it). Same clock for book updates and trades.
- **Exchange transaction time** (`transaction_time`, book updates only): Binance's transaction time for the update; verified `transaction_time_ms <= event_time_ms` on all 302,573 events (O12).
- **Exchange trade time** (`trade_time`, trades only): Binance's trade time; equals `event_time` in the observed data.
- **Local receipt time** (`received_time`): the timestamp the collector process stamped when the message arrived on the collection machine. This is the **earliest moment the information could exist inside the system**. Book and trade feeds are separate streams with independent receipt times.

## 4. Which clock was used in the original EXP-01 scientific analysis

**Exchange event time** (`event_time_ms`). Intervals are `(t0_event_time, t1_event_time]`; future states are the next h-th interval by `event_time`; `mid_change_bps`, touch-distance classification, and all EXP-01 endpoints are exchange-time based. The scientific analysis is entirely on the exchange clock.

## 5. Which clock can represent actual simulated information availability

**Local receipt time** (`received_time_ns`). Verified on all 6 hours:

- Book events: `received_time_ns/1e6 >= event_time_ms` for **all 302,573 events** (0 violations). Median book receipt lag ≈ 115–149 ms; p90 up to 2.35 s (hour 15); max 10.2 s (hour 15).
- Trades: `received_time/1e6 >= trade_time` for **all 699,364 trades** (0 violations). Median trade receipt lag ≈ 117–148 ms; p90 up to 1.03 s (hour 15); max 8.2 s (hour 15).

The receipt clock is a strict causal upper bound on the exchange clock, with a typical ~116 ms local delay — the same order of magnitude as the EXP-01 H1 horizon (~80–270 ms), so the choice of observation clock is first-order for the Paper Engine.

## 6. Is contributing trade receipt time recoverable from validated intermediate data?

**NO — this is the STOP condition.**

- D09 aggregates trades by `trade_time_ms` only (`src/liquidity/joint_flow.py` uses `trade_time`, `price`, `quantity`, `is_buyer_maker`, `trade_id`; **drops `received_time` and `event_time`**). The D09/D09B tapes store only aggregated flow quantities — no per-trade receipt time, no latest receipt time.
- D08C also drops the trade `received_time` (exchange-time alignment only).
- The trade `received_time` **does exist** in the raw validated trades parquet (gate0 input, read by `read_cryptohft`), but no validated intermediate carries it.

**Empirical consequence** (per-interval, all 6 hours): the latest contributing trade's receipt time exceeds the t1 book event's receipt time in **3.5–12.7% of firewall-eligible intervals** (hour 15: 12.71%, p90 +54.6 ms, max 7.6 s). Median excess is negative (−11 to −40 ms), so the t1 book receipt usually covers the trades — but assuming observability at t1 receipt would be wrong for a material minority, with a heavy tail in the most active hour. The trade-side availability gap is real and must not be approximated away.

## 7. Does the Paper Engine need one additional provenance field from an already-validated upstream layer?

**YES — one additive field in D09:**

`latest_trade_received_time_ns` = max `received_time` over trades with `trade_time` in `(t0, t1]` (the exact D09 interval convention); `NaN`/absent when the interval has no trades.

Derivation (causally justified, additive-only):
- In `src/liquidity/joint_flow.py::build_intervals`, the per-interval trade slice `ti` already exists; the field is `int(ti["received_time"].max())` when `n_trades > 0`.
- The D09B joint tape inherits it automatically: `touch_ecology.py` merges touch columns into the full D09 frame (`joint.merge(evt_df[touch_cols], ...)`), so all D09 columns flow through.
- **No existing column is modified** → frozen EXP-01 scientific results (exp01c/d/e, replication) are bit-for-bit unchanged. The D09/D09B regression tests compare against frozen CSVs; they would compare the frozen column set and validate the new column separately (test-suite adjustment only, no scientific change).
- The Paper Engine then reads it from the D09B joint `interval_fields` (already attached at the t1 event by PE-1).

This requires review approval before touching the upstream engineering layer, per the PE-3A stop condition. Alternative (Paper Engine reading the raw trades parquet directly) is rejected: it violates the PE-0 input rule (validated intermediates only).

## 8. Proposed definitions

```
signal_observable_time = max(
    t1_book_event_received_time_ns,          # D07 received_time_ns at the t1 event (already in event_fields)
    latest_trade_received_time_ns            # new D09 field, max trade receipt over (t0, t1]
)
decision_time          = signal_observable_time   # MODE A observation: earliest defensible decision moment
arrival_time           = decision_time + latency  # PE-4 (latency grid), NOT in PE-3
```

Causal chain (must hold everywhere, asserted by tests):

```
exchange_event_time(t1)  <=  signal_observable_time  <=  decision_time  <=  arrival_time
```

- Book side is already available to PE-3: `iter_events` keeps the full D07 row in `event_fields`, including `received_time_ns` (only `hour` is popped).
- Exchange time and observation time are **retained separately** (never overwritten): `event_time_ms` / `t1_event_time_ms` stay as the scientific clock; `signal_observable_time` / `decision_time` are new fields on the receipt clock.
- `signal_observable_time` never precedes required input availability by construction (max of the two availability bounds); `decision_time` stays in the same causal episode/state context (both bounds are properties of the t1 event's attached interval; no future event contributes).

## 9. Assumptions and limitations

- **Single collector clock**: `received_time` is stamped by the local collector; the audit assumes one consistent collector clock per stream (no cross-machine skew). This is the same clock the raw data was collected under; it is the best available proxy for "information availability".
- **Granularity**: receipt times are ns-resolution int64; exchange times ms-resolution int64. The observation clock is therefore strictly finer than the scientific clock.
- **Heavy tails are real**: hour 15 (the most active replication hour, 12,708 eligible events) has book receipt p99 ≈ 5.8 s and trade-receipt-vs-t1-receipt excess max ≈ 7.6 s. The Paper Engine's decision timing will inherit these tails; they are genuine availability constraints, not artifacts.
- **`event_time_ms` in the D09B joint is a duplicate of `t1_event_time_ms`** (exchange time) — it must never be used as the availability clock.
- **Upstream change is additive-only**; if approved, it must be implemented so that every existing D09/D09B column is byte-identical to the frozen tapes (frozen CSVs remain the reference).

---

## STOP condition statement

Validated intermediates are **insufficient** to determine when contributing trade information became observable (trade `received_time` is dropped at D09). Per the PE-3A stop condition, this audit **stops and reports the missing provenance** rather than approximating it away. The missing provenance is exactly one additive field — `latest_trade_received_time_ns` per interval in D09 (flowing to the D09B joint) — derivable from the already-validated raw trades parquet without changing any frozen EXP-01 scientific result. PE-3 implementation is **pending review approval** of this audit and of the upstream field addition.