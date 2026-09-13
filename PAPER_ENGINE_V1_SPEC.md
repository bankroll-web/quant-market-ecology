# Paper Engine V1 — Specification (PE-0)

**Status:** APPROVED 2026-09-13 (ChatGPT review checkpoint)
**Type:** New greenfield research module — NOT a refactor of an existing script
**Phase 2 acceptance:** D06 PASS · D07 PASS · D09 PASS · D09B PASS · EXP-01 PASS · ALL 9 REGRESSION SUITES PASS

---

## 1. Purpose

Paper Engine V1 is a **sequential, causal, simulated research engine**. It is NOT a
live-money execution system.

It answers: *Given an EXP-01-compatible market state that becomes observable at time t,
what happens if a simulated decision is made only after that information exists, then
subjected to latency and simplified execution assumptions?*

**Primary scientific question:** Can the EXP-01 state be observed, processed, and
simulated before the measured directional displacement disappears?

The engine must separate, in order:

1. signal formation
2. decision time
3. simulated arrival time
4. executable market state at arrival
5. simulated outcome measurement

**No lookahead is allowed.**

---

## 2. Input design

V1 does NOT start from raw parquet. It uses already validated/refactored intermediate data.

Preferred primary inputs:

- D07 event tape
- D09/D09B joint flow-liquidity tape
- reconstructed book-state information required for arrival-state lookup
- EXP-01-compatible features

Rationale: raw parquet reconstruction is already validated in D06/D07. Paper Engine V1
tests causal decision/execution mechanics — it must not re-solve raw ingestion.

```
validated upstream pipeline outputs  ->  paper engine
```

NOT:

```
raw parquet  ->  duplicate second reconstruction implementation
```

The engine must be architected so upstream validated modules can later feed it directly
during forward replay. **Do NOT duplicate D06/D07 logic inside paper_engine.**

---

## 3. Core event model

Operate sequentially by `event_time` inside verified episodes. For each valid event:

1. observe only information available at that event
2. update feature state
3. determine whether a frozen EXP-01 condition exists
4. create a paper decision only AFTER the relevant response state is observable
5. apply simulated processing/transport latency
6. locate the first valid market state at or after simulated arrival
7. record simulated entry reference
8. evaluate subsequent outcome causally

Formally:

```
RawEvent_t -> ValidatedState_t -> FeatureState_t -> SignalState_t
  -> Decision_t -> Arrival_(t + latency) -> PaperEntryState -> PaperOutcome
```

---

## 4. EXP-01 signal semantics (frozen — do not invent new thresholds)

- **Flow side:** BUY → opposing side = ASK; SELL → opposing side = BID
- **Near-touch:** 0–5 ticks from PRE-event touch
- **Response:**
  - response > 0 → REPLENISHMENT
  - response < 0 → DEPLETION
  - response == 0 → NEUTRAL
- Anchors remain subject to frozen temporal logic.

**Do NOT:** optimize tick width · change flow threshold · change response threshold ·
add momentum filters · add OBI filters · add volatility filters · add time-of-day
filters · add ML · select only favorable hours.

Paper Engine V1 must evaluate the frozen mechanism first.

---

## 5. Signal vs action

EXP-01's scientific result is not automatically an action rule. V1 supports two distinct
research modes:

**MODE A — OBSERVATION MODE**
Record EXP-01 state and later market movement without assuming an order. Purpose: verify
forward causal timing.

**MODE B — SIMULATED ACTION MODE**
Create a simple paper action AFTER state formation. Conceptual mapping (research only):

- DEPLETION after BUY aggression → paper long-direction hypothesis
- DEPLETION after SELL aggression → paper short-direction hypothesis
- REPLENISHMENT → comparator / control state

**Do NOT optimize this mapping after seeing historical results.** The engine preserves raw
scientific state even when no paper action is generated.

---

## 6. Decision time

Decision time occurs only after the response classification is observable. **Do NOT use
information from future valid L2 events to make the decision.**

- `t_decision >= timestamp at which response state is known`
- `t_arrival = t_decision + latency`
- Execution reference comes from the **first valid market state at or after t_arrival**
- **Never use the pre-response midpoint as simulated entry.**

---

## 7. Latency grid

| Latency (ms) | Role |
|---|---|
| 0 | Idealized diagnostic baseline ONLY — must NOT be presented as realistic execution |
| 5 | research scenario |
| 10 | research scenario |
| 25 | research scenario |
| 50 | research scenario |
| 100 | research scenario |
| 200 | research scenario |

- All latency scenarios must be reported. Do not select only the best latency afterward.
- Latency results stored separately so decay can be compared: `Edge(latency)`.
- Main question: does the relationship survive as latency increases?

---

## 8. Execution model V1

Keep execution assumptions intentionally simple and transparent. No precise queue-position
models (we only have L2 data, not L3). Two reference models:

**A. MIDPOINT DIAGNOSTIC MODEL**
Entry reference = midpoint at first valid state at/after arrival. Purpose: measure pure
information decay. NOT a realistic fill model.

**B. TOUCH / TAKER-LIKE DIAGNOSTIC MODEL**
Simulated buy → best ask at arrival; simulated sell → best bid at arrival. Purpose:
incorporate spread crossing in a simple observable way.

- Do NOT simulate exact queue position.
- Do NOT claim actual fills.
- Label outputs clearly as **simulated reference prices**.

---

## 9. Cost model V1

Separate raw information edge from assumed costs. Do NOT hard-code a single fee assumption
as truth. Configurable cost fields, at minimum:

- `spread_cost_bps`
- `fee_bps`
- `slippage_bps`

Default research scenarios:

- ZERO-COST DIAGNOSTIC
- CONFIGURABLE COST SCENARIOS

Engine outputs:

- `gross_directional_bps`
- `spread_cost_bps`
- `fee_bps`
- `slippage_bps`
- `net_simulated_bps`

```
net_simulated_bps = gross_directional_bps - spread_cost_bps - fee_bps - slippage_bps
```

**Do NOT claim profitability from zero-cost results.**

---

## 10. Exit / outcome model

V1 does not optimize exits. Use frozen event horizons first.

- Primary horizons: **H3, H5, H10**
- H1: diagnostic only
- Outcome measurement remains **episode-safe** — no crossing episode boundaries.

For each simulated entry:

1. record midpoint and/or touch reference at arrival
2. locate subsequent valid L2 events within the SAME episode
3. measure directional midpoint displacement and directional executable-reference
   displacement where available

**No stop-loss or take-profit logic in V1.**

---

## 11. Latency/horizon clocks — preserve BOTH

EXP-01 horizons are relative to the response event; paper entry occurs later because of
latency. Store both clocks explicitly:

**A. ORIGINAL SCIENTIFIC CLOCK**
response event → H1/H3/H5/H10

**B. PAPER-ENTRY CLOCK**
simulated arrival → subsequent market evolution

**Do NOT silently reinterpret H3/H5/H10 as entry-relative horizons.** This answers two
questions: (1) did the frozen scientific effect reproduce? (2) how much remained after
simulated latency?

---

## 12. Output schema — event-level paper ledger

| Field | Notes |
|---|---|
| `source_hour` | |
| `episode_id` | |
| `event_index` | |
| `event_time` | |
| `flow_side` | |
| `signed_flow_qty` | |
| `total_flow_qty` | |
| `flow_purity` | if available |
| `best_bid` | |
| `best_ask` | |
| `mid` | |
| `spread` | |
| `bid_depth_top5` | |
| `ask_depth_top5` | |
| `obi_top5` | if available |
| `near_touch_bid_net` | |
| `near_touch_ask_net` | |
| `response_value` | |
| `response_class` | |
| `signal_eligible` | |
| `signal_direction` | |
| `decision_time` | |
| `latency_ms` | |
| `arrival_time` | |
| `arrival_event_index` | |
| `arrival_bid` | |
| `arrival_ask` | |
| `arrival_mid` | |
| `arrival_spread` | |
| `entry_reference_model` | |
| `entry_reference_price` | |
| `scientific_h1_bps` | scientific clock |
| `scientific_h3_bps` | scientific clock |
| `scientific_h5_bps` | scientific clock |
| `scientific_h10_bps` | scientific clock |
| `post_arrival_1event_bps` | paper-entry clock |
| `post_arrival_3event_bps` | paper-entry clock |
| `post_arrival_5event_bps` | paper-entry clock |
| `post_arrival_10event_bps` | paper-entry clock |
| `gross_directional_bps` | |
| `spread_cost_bps` | |
| `fee_bps` | |
| `slippage_bps` | |
| `net_simulated_bps` | |
| `episode_end_before_horizon` | |
| `arrival_missing` | |
| `outcome_missing` | |

All rows must remain auditable.

---

## 13. Summary outputs

**A. SIGNAL SUMMARY** — counts by response class, flow side, source hour, episode.

**B. LATENCY DECAY SUMMARY** — for each latency: n, mean directional bps, median
directional bps, positive-rate, bootstrap CI where appropriate.

**C. RESPONSE COMPARISON** — DEPLETION vs REPLENISHMENT at each latency.

**D. SIDE ROBUSTNESS** — BUY and SELL separately.

**E. HOUR ROBUSTNESS** — each source hour separately.

**F. EPISODE-EQUAL SUMMARY** — one episode one vote where scientifically appropriate.
Do not rely only on row-weighted results.

---

## 14. No-optimization rule

Frozen May data remain regression/evaluation data. Paper Engine V1 may use them to:
validate causality · validate no-lookahead · measure information decay · test engineering
mechanics.

It must NOT use them to optimize: latency · tick width · flow thresholds · response
thresholds · exits · filters · position sizing · cost assumptions · model hyperparameters.

All latency scenarios must be reported. No best-latency selection.

---

## 15. Testing requirements

| # | Test |
|---|---|
| 1 | **No lookahead:** no feature uses timestamps > decision_time |
| 2 | **Arrival causality:** arrival event timestamp >= decision_time + latency |
| 3 | **Episode containment:** entry/outcome never crosses episode |
| 4 | **Latency monotonic arrival:** higher latency cannot map to an earlier event |
| 5 | **0 ms diagnostic:** arrival state is first valid state at/after decision |
| 6 | **BUY/SELL execution reference:** BUY → ask for touch model; SELL → bid for touch model |
| 7 | **Scientific horizons unchanged:** frozen H1/H3/H5/H10 results remain untouched |
| 8 | **Determinism:** same input/config → identical ledger |
| 9 | **Missing future states handled explicitly** |
| 10 | **Upstream frozen regression remains green** — `run_tests.py` must continue to pass all existing 9 suites |

---

## 16. Package structure (proposed)

```
src/paper_engine/
    __init__.py
    config.py        # latency grid, cost scenarios, horizons (PE-0 constants)
    events.py        # sequential event iterator over validated tapes (PE-1)
    state.py         # causal feature/state reconstruction (PE-1)
    signal.py        # frozen EXP-01 signal-state reconstruction (PE-2)
    latency.py       # decision/arrival timestamps + latency grid (PE-3/PE-4)
    execution.py     # midpoint + touch/taker-like reference models (PE-5/PE-6)
    outcomes.py      # episode-safe outcome measurement, both clocks (PE-7)
    accounting.py    # cost-accounting layer (PE-8)
    metrics.py       # summary tables A–F (PE-9)
    ledger.py        # event-level paper ledger assembly (PE-9)
    replay.py        # full historical research replay driver (PE-10)

tests/
    test_paper_engine_causality.py    # tests 1–5, 9
    test_paper_engine_latency.py      # tests 2, 4, 5
    test_paper_engine_execution.py    # tests 6, 7
    test_paper_engine_determinism.py  # test 8
```

**Do not over-engineer prematurely.** Build the minimum clean architecture needed for V1;
files that stay trivial during the build may be consolidated rather than padded.

---

## 17. Phased build order

| Gate | Deliverable | Tests required before next gate |
|---|---|---|
| PE-0 | Written spec only. No code. | — |
| PE-1 | Sequential event iterator + causal state | causality tests |
| PE-2 | Frozen EXP-01 signal-state reconstruction | signal vs frozen EXP-01 semantics |
| PE-3 | Decision/arrival timestamps | no-lookahead, arrival causality |
| PE-4 | Latency grid | monotonic arrival, 0 ms diagnostic |
| PE-5 | Midpoint diagnostic execution model | execution reference tests |
| PE-6 | Touch/taker-like diagnostic model | BUY→ask / SELL→bid tests |
| PE-7 | Outcome measurement | episode containment, both clocks |
| PE-8 | Cost-accounting layer | net = gross − spread − fee − slippage |
| PE-9 | Event ledger + summaries | ledger schema, determinism |
| PE-10 | Full historical research replay | full suite + upstream regression green |

Each phase must pass tests before the next begins.

---

## 18. Scientific distinction

Paper Engine V1 is NOT built to prove a profitable strategy. It tests whether a replicated
microstructure effect remains observable under causal timing and simplified simulated
execution assumptions. Acceptable conclusions:

- **A.** Effect survives timing and simple cost assumptions.
- **B.** Effect survives scientifically but disappears under latency.
- **C.** Effect survives latency but disappears after spread/cost assumptions.
- **D.** Effect is too small for simulated execution despite being statistically real.

ALL FOUR ARE ACCEPTABLE. Do not modify the system to force outcome A.

---

## 19. Current primary question

**Can EXP-01 information survive the delay between state observation → decision →
simulated arrival?**

That is the purpose of this engine.

---

## 20. Approval record

- Paper Engine V1 SPEC DESIGN: **APPROVED** (ChatGPT review checkpoint, 2026-09-13)
- Phase 2 formally accepted: D06/D07/D09/D09B/EXP-01 PASS; all 9 regression suites PASS
- Build order: create this spec (PE-0) → return proposed file structure + PE-0 spec for
  review → implement PE-1 only after review approval.