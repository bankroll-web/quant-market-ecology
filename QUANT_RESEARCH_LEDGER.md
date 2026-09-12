# QUANT RESEARCH LEDGER — Human-Readable Mirror

> **Canonical source of truth:** `QUANT_RESEARCH_LEDGER.json` (machine-readable).
> This markdown file is a mirror and must be regenerated from the JSON whenever the JSON changes.

**Project:** BTC Quantitative Market-Ecology Research System
**Status:** ACTIVE — phase: IndependentReplication → UnifiedState
**Ledger version:** 1.0 · **Created:** 2026-09-12

**Core thesis:** Price is an output/coordinate of market state, not the complete state itself. The same market action can have different consequences depending on surrounding state.

---

## EXP-01 — Absorption vs Yielding (CryptoHFT microstructure)

**Status:** ✅ DISCOVERY COMPLETE / ✅ INDEPENDENT REPLICATION COMPLETE / 🔒 FROZEN

**Hypothesis:** Conditional on aggressive trade flow, depletion of opposing displayed liquidity within 0–5 ticks is associated with greater subsequent flow-direction midpoint displacement than replenishment.

**Data:** Discovery `2026-05-25_00` · Replication 5 untouched hours (`04`, `12`, `18`, `15`, `21`)

**Frozen definitions:**
- Flow: `signed_flow_qty > 0 → BUY`, `< 0 → SELL`; opposing side = ASK for BUY, BID for SELL
- Near-touch region: 0–5 ticks from PRE-event opposing touch
- Response: `opposing_near_net_qty > 0 → REPLENISHMENT`, `< 0 → DEPLETION`, `== 0 → NEUTRAL`
- Firewall: `trades_exactly_at_t1 == 0 AND total_flow_qty > 0 AND signed_flow_qty != 0`
- Horizons: H1 diagnostic · **H3/H5/H10 primary** (literal consecutive valid L2 events, same episode)
- Ordering: future shifts constructed BEFORE selecting starting events (never filter-then-shift)

**Discovery (3,733 events; DEP 3,254 / REP 439 / NEU 40):**

| Horizon | Pooled diff (bps) | Equal-episode mean (bps) | 95% CI | Verdict |
|---|---|---|---|---|
| H1 | +0.014925 | +0.005608 | [−0.023, +0.026] | ❌ FAIL (diagnostic) |
| H3 | +0.038168 | +0.032646 | [+0.015, +0.050] | ✅ PASS |
| H5 | +0.055901 | +0.048139 | [+0.022, +0.073] | ✅ PASS |
| H10 | +0.073965 | +0.083296 | [+0.025, +0.148] | ✅ PASS |

**Replication (27,137 events; 502 episodes):**

| Gate | Result |
|---|---|
| Gate 0 raw data | 5/5 PASS |
| Gate 1 canonical D06 | 5/5 PASS (counts match discovery methodology exactly) |
| Gate 1b D07 | 5/5 PASS (D07 = D06 counts exactly) |
| Gate 2 D08C sync | 5/5 PASS (0 dup IDs, 0 negative lags/leads, touch sanity ≥ 97.9%) |
| Gate 3 D09 | 5/5 PASS (N = valid events − episodes holds) |

| Horizon | Equal-episode mean (bps) | 95% CI | Bootstrap P(>0) | Sign-flip p | Verdict |
|---|---|---|---|---|---|
| H1 | +0.015046 | [+0.0106, +0.0200] | 1.0 | 0.00005 | Diagnostic only — NOT promoted |
| H3 | +0.016906 | [+0.0002, +0.0314] | 0.9763 | 0.0144 | ✅ SURVIVES |
| H5 | +0.034735 | [+0.0222, +0.0480] | 1.0 | 0.00005 | ✅ SURVIVES |
| H10 | +0.042933 | [+0.0275, +0.0589] | 1.0 | 0.00005 | ✅ SURVIVES |

**Robustness:** 5/5 untouched hours same sign at H3/H5/H10 · flow/depth control survives · one-sided aggression survives · effect sparse (zero rates 43–48%; positive among nonzero 79–88% — **NOT trading accuracy**) · concentrated (top 20% of episodes ≈ 78–82% of effect).

**Verdict:** ✅ PASS — strongest empirical mechanism in the project. **Not** causal, profitable, or tradable.

**Usage policy:** Debugging / unit tests / reproducing recorded results / regression tests ONLY. Never for threshold or hyperparameter optimization.

---

## DBR — Directional Boundary Re-Anchoring (FXSSI retail ecology)

**Status:** ✅ DISCOVERY COMPLETE / ⏳ PROSPECTIVE REPLICATION PENDING · 🔒 FROZEN spec

**Hypothesis:** BTC down + long stop boundary re-anchor downward → future longward retail reallocation; BTC up + short stop boundary re-anchor upward → future shortward retail reallocation.

**Frozen definitions:**
- DOWN-DBR: `BTC 20m return < 0 AND long cluster changed AND long migration < 0`
- UP-DBR: `BTC 20m return > 0 AND short cluster changed AND short migration > 0`
- Primary horizon: 20 min · Secondary: 40 / 60 min
- Discovery cutoff: **2026-09-09 18:20 UTC** — only strictly later timestamps are prospective

**Discovery (20-min results):**

| Event | Counter-reallocation | Control | Difference | SMD |
|---|---|---|---|---|
| DOWN DBR | +0.7500 | +0.0934 | +0.6567 | 0.617 |
| UP DBR | +0.6245 | −0.1241 | +0.7487 | 0.677 |

**Known confound:** DBR events had larger BTC moves; linear absolute-return controls may not fully remove magnitude confounding. **Not causal or tradable.**

**Prospective status:** 0 prospective rows (FXSSI access ended ~Sep 11; expected to resume ~Tuesday). **Do not modify the experiment while waiting.**

---

## FXSSI Experiments (discovery-stage records)

| ID | Result | Status |
|---|---|---|
| EXP-19 | Same retail reallocation state can occur during opposite BTC directions → not a deterministic directional signal | Discovery complete |
| EXP-20 | BTC impulse → retail response stronger than retail → future BTC; counter-directional reallocation | Discovery complete |
| EXP-21 | Broad symmetric hypothesis falsified → refined Candidate A1 (large displacement → counter-directional reallocation; downside broader) | Discovery complete |
| EXP-22 | **PASS — price is not state descriptively** (ecology NN error 14.65 vs price-only 18.71 at 20m) | Discovery complete |
| EXP-23 | Recurring ecological organization detected (10/16 states, top 4 ≈ 86.7%) — not a trading rule | Discovery complete |
| EXP-24–26 | Stop clusters ~83.6% anchored; stock/flow + reset; DBR candidate produced | Discovery complete |

---

## Older Lab2 (historical — not centerpiece)

| ID | Result |
|---|---|
| Gen3 | Historical N=269 mean gross ≈ +5.7552 bps; prospective N=56 net ≈ +3.4071 bps, CI included zero |
| Gen4-E | Only ~2 candidates |

---

## Discrepancies

| ID | Detail | Action |
|---|---|---|
| D1 | `build_may_5m_bars.py` **absent from disk** (recursive search 2026-09-12); only `may_5m_bars.csv` survives in `Audit_V2_1`. **Status: LEGACY / MISSING ARTIFACT / NON-BLOCKING.** Historical role: raw trades → `may_5m_bars.csv`; NOT part of canonical EXP-01 chain; absence does not invalidate EXP-01 | Preserve `may_5m_bars.csv`; recover script separately from backup/Recycle Bin; do NOT recreate from memory or substitute another script |
| D2 | `may_5m_bars.csv` at `Audit_V2_1\may_5m_bars.csv`, not Documents root | Recorded; no action |
| D3 | Ledger did not exist before 2026-09-12 | Resolved by creation |

## Observations

- **O1** Rejected gate-1 script preserved (`exp01_replication_gate1.py`) — never use; canonical is `gate1_canonical.py`
- **O2** `exp01_replication_gate0_BACKUP.py` preserved
- **O3** Pre-canonical EXP-01 iterations (`exp01_absorption_vs_yielding.py`, `exp01b_corrected_l2_horizons.py`) preserved as history
- **O4** `BTC_V3` = separate Binance ML pipeline — **KEEP FULLY SEPARATE** until separately audited and approved
- **O5** No git on machine (winget available); approved repo root `Documents\quant-market-ecology`; do NOT init at Documents root
- **O6** No tests existed before Phase 1 scaffolding

---

## Next objectives

1. ~~Freeze EXP-01~~ (done — do not mine the six May hours further)
2. ~~Regression tests~~ (DONE 2026-09-12 — 28 checks green)
3. **Phase 2: behavior-preserving refactor into `src/` modules** ← current (APPROVED 2026-09-12)
4. Paper Engine V1 (sequential replay, causal ordering, latency grid, cost model)
5. Unified state model (M_t + R_t, hierarchical/multiscale — NOT naive merge)
6. Forward validation on genuinely new data with frozen rules

## Phase 2 approval (2026-09-12 — ChatGPT review checkpoint)

**Scope: REFACTORING ONLY.** Allowed: extract duplicated logic into `src/` modules, improve organization/type hints/docstrings/error handling/logging, centralize config/path handling, add tests, create reusable D06/D07/D09/D09B components.

**NOT allowed:** change any mathematical definition, D06 bridge/continuity logic, aggressor classification, D09 interval semantics `(t0, t1]`, exact-t1 handling, 0–5 tick definition, depletion/replenishment classification, H1/H3/H5/H10 construction, flow/depth controls; promote H1; remove May-26 15; optimize thresholds; add predictive filters; train ML; optimize historical PnL; modify frozen CSVs/specs; overwrite original canonical scripts.

**Validation:** rerun regression suite after each extraction. Canonical → frozen output ← refactored must match exactly (row counts, episode counts, sequence integrity, timestamps, ordering, liquidity quantities, interval identity, spatial classifications, response classifications, horizons, final statistics). **Any unexplained discrepancy = STOP and report.** Do not fix tests to accept changed results.

**Git checkpoints:** Commit 1 "Establish frozen research baseline" · Commit 2 "Add regression tests for canonical pipeline" · then small per-subsystem commits.

**BTC_V3:** fully separate — do not import/copy/merge/refactor/use during Phase 2.

## Main risks

Latency (~80–270 ms) · transaction costs · execution observability · fill uncertainty (L2) · long-run stability · state dependence (many zero episodes) · regime dependence (May-26 15) · multiscale synchronization · multiple testing · overfitting.

---

*Mirror of QUANT_RESEARCH_LEDGER.json v1.0 — regenerate from JSON after any edit.*