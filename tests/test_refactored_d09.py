"""
Refactor validation: refactored D09 joint flow/liquidity tape must
reproduce frozen outputs exactly.

Runs src.liquidity.joint_flow.process_hour on all six hours (discovery +
5 replication) and compares:
  - per-hour records DataFrame vs frozen <hour>_d09_joint_flow_liquidity_tape.csv
    (exact, all columns)
  - discovery records vs frozen d09_joint_flow_liquidity_tape.csv (shared
    columns; discovery output has no hour column)
  - result counters vs frozen gate3_d09_joint_tape_summary.csv

Book input is the frozen D07 event-tape CSV read with the DEFAULT parser,
matching the canonical D09 input (the frozen d09 outputs embed the
default-parser last-ULP artifacts; see src/liquidity/joint_flow.py).
Frozen d09 CSVs are read with float_precision='round_trip' (ledger O7).
UTC columns are normalized with pd.to_datetime(..., utc=True,
format='mixed') and cast to datetime64[us, UTC] on both sides (O8).

Runtime: ~2-4 minutes (six hours, parallel 3 workers, checkpointed).

Run:  python tests/test_refactored_d09.py
"""
import multiprocessing
import os
import pickle
import sys

import pandas as pd
from pandas.testing import assert_frame_equal

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from src.liquidity.joint_flow import process_hour  # noqa: E402

ROOT = os.path.join(os.path.dirname(__file__), "..")
FROZEN = os.path.join(ROOT, "data", "frozen")
RAW = os.path.join(ROOT, "data", "raw")
CHECKPOINT_DIR = os.path.join(ROOT, "tests", "logs", "checkpoints", "d09")

REPLICATION_HOURS = [
    "2026-05-25_04",
    "2026-05-25_12",
    "2026-05-25_18",
    "2026-05-26_15",
    "2026-05-26_21",
]
DISCOVERY_HOUR = "2026-05-25_00"

UTC_COLS = ["t0_utc", "t1_utc"]

# gate3_d09_joint_tape_summary.csv columns (output_file excluded).
SUMMARY_COLS = [
    "hour",
    "valid_l2_intervals",
    "episodes_with_intervals",
    "intervals_with_trade_rows",
    "positive_qty_flow_intervals",
    "trades_assigned",
    "trades_exactly_at_t1",
    "intervals_with_exact_t1",
    "clean_intervals",
    "clean_flow_intervals",
    "interval_ms_mean",
    "interval_ms_median",
    "interval_ms_p99",
    "interval_ms_max",
]


def read_frozen(name):
    return pd.read_csv(
        os.path.join(FROZEN, name),
        float_precision="round_trip",
    )


def normalize_utc(df):
    """Unify UTC columns to datetime64[us, UTC] on both sides (O8)."""
    df = df.copy()
    for col in UTC_COLS:
        if col in df.columns:
            df[col] = pd.to_datetime(
                df[col], utc=True, format="mixed"
            ).astype("datetime64[us, UTC]")
    return df


def check(name, cond, detail=""):
    status = "PASS" if cond else "FAIL"
    print(f"[{status}] {name}" + (f"  ({detail})" if detail else ""))
    return cond


def _process_one(hour):
    """Top-level worker (picklable under Windows spawn)."""
    if hour == DISCOVERY_HOUR:
        book_csv = os.path.join(FROZEN, "d07_liquidity_event_tape.csv")
    else:
        book_csv = os.path.join(FROZEN, f"{hour}_d07_liquidity_event_tape.csv")
    records_df, result = process_hour(hour, book_csv, RAW)
    return hour, records_df, result


def _checkpoint_path(hour):
    return os.path.join(CHECKPOINT_DIR, f"{hour}.pkl")


def test_replication_records_exact(results):
    ok = True
    for hour in REPLICATION_HOURS:
        records_df = normalize_utc(results[hour][0])
        frozen = normalize_utc(read_frozen(f"{hour}_d09_joint_flow_liquidity_tape.csv"))
        try:
            assert_frame_equal(
                records_df.reset_index(drop=True),
                frozen.reset_index(drop=True),
                check_exact=True,
                check_dtype=True,
                obj=f"refactored vs frozen {hour} d09",
            )
            ok = check(f"replication {hour}: d09 records identical", True,
                       f"rows={len(records_df)}") and ok
        except AssertionError as exc:
            ok = check(f"replication {hour}: d09 records identical", False,
                       str(exc).splitlines()[0]) and ok
    return ok


def test_discovery_records_exact(results):
    records_df = normalize_utc(results[DISCOVERY_HOUR][0])
    frozen = normalize_utc(read_frozen("d09_joint_flow_liquidity_tape.csv"))
    shared = [c for c in records_df.columns if c != "hour"]
    try:
        assert_frame_equal(
            records_df[shared].reset_index(drop=True),
            frozen[shared].reset_index(drop=True),
            check_exact=True,
            check_dtype=True,
            obj="refactored vs frozen discovery d09",
        )
        return check("discovery: d09 records identical (shared columns)", True,
                     f"rows={len(records_df)}")
    except AssertionError as exc:
        return check("discovery: d09 records identical (shared columns)", False,
                     str(exc).splitlines()[0])


def test_summary_matches_gate3(results):
    g3 = read_frozen("gate3_d09_joint_tape_summary.csv")
    ok = True
    for hour in REPLICATION_HOURS:
        result = results[hour][1]
        row = g3[g3["hour"] == hour].iloc[0]
        for col in SUMMARY_COLS:
            got = result[col]
            exp = row[col]
            if isinstance(exp, float) and pd.isna(exp):
                match = pd.isna(got)
            else:
                match = got == exp
            ok = check(f"summary {hour}: {col}", bool(match), f"got={got} exp={exp}") and ok
    return ok


def main():
    os.makedirs(CHECKPOINT_DIR, exist_ok=True)
    hours = REPLICATION_HOURS + [DISCOVERY_HOUR]
    results = {}
    todo = []
    for hour in hours:
        cp = _checkpoint_path(hour)
        if os.path.exists(cp):
            with open(cp, "rb") as f:
                results[hour] = pickle.load(f)
            print(f"  {hour}: loaded from checkpoint")
        else:
            todo.append(hour)

    if todo:
        print(f"Building {len(todo)} hours (3 parallel workers)...")
        with multiprocessing.Pool(processes=3) as pool:
            for hour, records_df, result in pool.imap_unordered(_process_one, todo):
                results[hour] = (records_df, result)
                with open(_checkpoint_path(hour), "wb") as f:
                    pickle.dump((records_df, result), f)
                print(f"  {hour}: {len(records_df)} records")

    checks = [
        test_replication_records_exact(results),
        test_discovery_records_exact(results),
        test_summary_matches_gate3(results),
    ]
    n_pass = sum(checks)
    n_fail = len(checks) - n_pass
    print(f"\nRefactored D09: {n_pass} passed, {n_fail} failed")
    return 0 if n_fail == 0 else 1


if __name__ == "__main__":
    sys.exit(main())