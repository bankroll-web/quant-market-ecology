# quant-market-ecology

BTC Quantitative Market-Ecology Research System — engineering workspace.

**Status:** ACTIVE · Phase: IndependentReplication → UnifiedState
**Scientific record:** `QUANT_RESEARCH_LEDGER.json` (canonical) + `QUANT_RESEARCH_LEDGER.md` (mirror)

## What this repo is

This is the **engineering and implementation workspace** for the research project described in the Master Handoff. It contains:

- **Copies** of the canonical research scripts and frozen outputs (originals remain untouched in `C:\Users\USER\Documents`)
- **Regression tests** that lock the frozen scientific record so refactoring cannot silently change results
- The **research ledger** (machine-readable + human-readable)
- Future home of the **Paper Engine V1** and the **unified state model**

## Discipline rules (non-negotiable)

1. **EXP-01 is FROZEN.** Do not change: 0–5 tick region, depletion/replenishment definitions, H3/H5/H10 primary horizons, H1 diagnostic status, aggressor mapping, timestamp-clean starting rule, verified-episode reconstruction, future-event horizon construction, BUY/SELL pooling, controls.
2. **Do not optimize against the six May hours** (discovery + 5 replication). They are research history — debugging and regression tests only.
3. **DBR is FROZEN.** No threshold optimization, no rule changes after prospective outcomes appear, no deleting unfavorable events.
4. **`BTC_V3` stays fully separate** until separately audited and explicitly approved.
5. **Removals are NOT cancellations.** Never describe D07 removals as known cancellations.
6. **No causality / profitability / tradability claims.** The effect is sparse, state-dependent, and unproven economically.
7. **If engineering requires changing a scientific definition: STOP AND REPORT IT.** Never silently fix the research definition.

## Repository layout

```
quant-market-ecology/
├── QUANT_RESEARCH_LEDGER.json     # canonical machine-readable research record
├── QUANT_RESEARCH_LEDGER.md       # human-readable mirror (regenerate from JSON)
├── run_tests.py                   # runs the full regression suite
├── configs/
│   ├── exp01_frozen.json          # copy of EXP01_FROZEN_REPLICATION_SPEC.json
│   └── dbr_frozen.json            # copy of DBR_FROZEN_SPEC_20260910.json
├── data/
│   └── frozen/                    # frozen outputs (the scientific record)
├── scripts/                       # copies of canonical research scripts
├── src/                           # refactored modules (Phase 2, after tests pass)
│   ├── ingestion/  book/  flow/  liquidity/
│   ├── state/  signals/  simulation/  metrics/
├── tests/                         # regression tests (Phase 1 — DONE)
└── docs/                          # methodology + data dictionary (planned)
```

## Running the regression tests

Requires Python 3.13 + pandas (pyarrow/zstandard needed only for raw-data pipelines).

```
python run_tests.py
```

Current suites (all lock frozen values from the handoff and the frozen CSVs):

| Suite | Locks |
|---|---|
| `test_d06_reconstruction.py` | D06 verified book reconstruction counts (discovery + 5 replication hours) |
| `test_d09_intervals.py` | Interval identity `N = valid_events − episodes` (discovery + replication) |
| `test_d09b_touch.py` | Touch-distance ecology consistency, bucket net = add − remove identity |
| `test_exp01_regression.py` | EXP-01 discovery + replication frozen values (counts, means, CIs, p-values) |

**Gate rule:** any refactor that changes a frozen number is rejected. Tests must stay green before, during, and after refactoring.

## Data provenance

- Raw order books: `C:\Users\USER\Documents\Audit_V2_1\Raw_Orderbooks` (6 hours, OUTER_ZSTD_PARQUET)
- Raw trades: `C:\Users\USER\Documents\CryptoHFT_Trades_8Hours` (8 hours, OUTER_ZSTD_PARQUET)
- FXSSI retail ecology: `C:\Users\USER\AppData\Roaming\MetaQuotes\Terminal\Common\Files\fxssi.com`
- Frozen outputs: `data/frozen/` (copies; originals in `Documents` are the authoritative record)

## Next steps

1. ✅ Phase 0: repo scaffolding + research ledger
2. ✅ Phase 1: regression tests (28 checks green)
3. ⏳ Phase 2: behavior-preserving refactor into `src/` modules (only after tests pass)
4. ⏳ Phase 3: Paper Engine V1 (sequential replay, causal ordering, latency grid, cost model)
5. ⏳ Phase 4: forward validation on genuinely new data with frozen rules