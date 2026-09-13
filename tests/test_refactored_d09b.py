"""
Refactor validation: refactored D09B touch-distance ecology must
reproduce frozen outputs exactly.

Runs src.liquidity.touch_ecology.process_hour on all six hours (discovery +
5 replication) and compares:
  - per-hour event table vs frozen <hour>_d09b_touch_distance_book_events.csv
    (exact, all columns)
  - per-hour augmented joint table vs frozen <hour>_d09b_joint_flow_touch_ecology.csv
    (exact, all columns)
  - result counters vs values derived from the frozen files
    (match rate, clean/signed interval counts, gate)

Book input is the raw CryptoHFT orderbook parquet; the D09 joint tape is
read with the DEFAULT parser, matching the canonical D09B input (the
frozen d09b joint outputs embed the default-parser last-ULP artifacts;
see src/liquidity/touch_ecology.py). Frozen d09b CSVs are read with
float_precision='round_trip' (ledger O7). UTC columns are normalized with
pd.to_datetime(..., utc=True, format='mixed') and cast to
datetime64[us, UTC] on both sides (O8).

Runtime: ~10-20 minutes first run (six hours, parallel 3 workers,
checkpointed); instant on re-run.

Run:  python tests/test_refactored_d09b.py
"""
import multiprocessing
import os
import pickle
import sys

import pandas as pd
from pandas.testing import assert_frame_equal

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from src.liquidity.touch_ecology import process_hour  # noqa: E402

ROOT = os.path.join(os.path.dirname(__file__), "..")
FROZEN = os.path.join(ROOT, "data", "frozen")
RAW = os.path.join(ROOT, "data", "raw")
CHECKPOINT_DIR = os.path.join(ROOT, "tests", "logs", "checkpoints", "d09b")

REPLICATION_HOURS = [
    "2026-05-25_04",
    "2026-05-25_12",
    "2026-05-25_18",
    "2026-05-26_15",
    "2026-05-26_21",
]
DISCOVERY_HOUR = "2026-05-25_00"

EVT_UTC_COLS = ["event_time_utc"]
JOINT_UTC_COLS = ["t0_utc", "t1_utc"]


def read_frozen(name):
    return pd.read_csv(
        os.path.join(FROZEN, name),
        float_precision="round_trip",
    )


def normalize_utc(df, cols):
    """Unify UTC columns to datetime64[us, UTC] on both sides (O8)."""
    df = df.copy()
    for col in cols:
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
        d09_csv = os.path.join(FROZEN, "d09_joint_flow_liquidity_tape.csv")
    else:
        d09_csv = os.path.join(FROZEN, f"{hour}_d09_joint_flow_liquidity_tape.csv")
    evt_df, aug_df, result = process_hour(hour, RAW, d09_csv)
    return hour, evt_df, aug_df, result


def _checkpoint_path(hour):
    return os.path.join(CHECKPOINT_DIR, f"{hour}.pkl")


def test_replication_events_exact(results):
    ok = True
    for hour in REPLICATION_HOURS:
        evt_df = normalize_utc(results[hour][0], EVT_UTC_COLS)
        frozen = normalize_utc(
            read_frozen(f"{hour}_d09b_touch_distance_book_events.csv"),
            EVT_UTC_COLS,
        )
        try:
            assert_frame_equal(
                evt_df.reset_index(drop=True),
                frozen.reset_index(drop=True),
                check_exact=True,
                check_dtype=True,
                obj=f"refactored vs frozen {hour} d09b events",
            )
            ok = check(f"replication {hour}: d09b events identical", True,
                       f"rows={len(evt_df)}") and ok
        except AssertionError as exc:
            ok = check(f"replication {hour}: d09b events identical", False,
                       str(exc).splitlines()[0]) and ok
    return ok


def test_discovery_events_exact(results):
    evt_df = normalize_utc(results[DISCOVERY_HOUR][0], EVT_UTC_COLS)
    frozen = normalize_utc(
        read_frozen("d09b_touch_distance_book_events.csv"), EVT_UTC_COLS
    )
    try:
        assert_frame_equal(
            evt_df.reset_index(drop=True),
            frozen.reset_index(drop=True),
            check_exact=True,
            check_dtype=True,
            obj="refactored vs frozen discovery d09b events",
        )
        return check("discovery: d09b events identical", True,
                     f"rows={len(evt_df)}")
    except AssertionError as exc:
        return check("discovery: d09b events identical", False,
                     str(exc).splitlines()[0])


def test_replication_joint_exact(results):
    ok = True
    for hour in REPLICATION_HOURS:
        aug_df = normalize_utc(results[hour][1], JOINT_UTC_COLS)
        frozen = normalize_utc(
            read_frozen(f"{hour}_d09b_joint_flow_touch_ecology.csv"),
            JOINT_UTC_COLS,
        )
        try:
            assert_frame_equal(
                aug_df.reset_index(drop=True),
                frozen.reset_index(drop=True),
                check_exact=True,
                check_dtype=True,
                obj=f"refactored vs frozen {hour} d09b joint",
            )
            ok = check(f"replication {hour}: d09b joint identical", True,
                       f"rows={len(aug_df)}") and ok
        except AssertionError as exc:
            ok = check(f"replication {hour}: d09b joint identical", False,
                       str(exc).splitlines()[0]) and ok
    return ok


def test_discovery_joint_exact(results):
    aug_df = normalize_utc(results[DISCOVERY_HOUR][1], JOINT_UTC_COLS)
    frozen = normalize_utc(
        read_frozen("d09b_joint_flow_touch_ecology.csv"), JOINT_UTC_COLS
    )
    try:
        assert_frame_equal(
            aug_df.reset_index(drop=True),
            frozen.reset_index(drop=True),
            check_exact=True,
            check_dtype=True,
            obj="refactored vs frozen discovery d09b joint",
        )
        return check("discovery: d09b joint identical", True,
                     f"rows={len(aug_df)}")
    except AssertionError as exc:
        return check("discovery: d09b joint identical", False,
                     str(exc).splitlines()[0])


def test_counters_match_frozen(results):
    ok = True
    for hour in REPLICATION_HOURS + [DISCOVERY_HOUR]:
        result = results[hour][2]
        frozen_evt = read_frozen(
            f"{hour}_d09b_touch_distance_book_events.csv"
            if hour != DISCOVERY_HOUR
            else "d09b_touch_distance_book_events.csv"
        )
        frozen_joint = read_frozen(
            f"{hour}_d09b_joint_flow_touch_ecology.csv"
            if hour != DISCOVERY_HOUR
            else "d09b_joint_flow_touch_ecology.csv"
        )

        expected = {
            "valid_event_records": len(frozen_evt),
            "d09_rows": len(frozen_joint),
            "augmented_rows": len(frozen_joint),
            "touch_response_match": float(
                frozen_joint["event_time_ms"].notna().mean()
            ),
            "all_intervals": len(frozen_joint),
            "clean_intervals": int(
                (frozen_joint["trades_exactly_at_t1"] == 0).sum()
            ),
            "removed_exact_t1": int(
                (frozen_joint["trades_exactly_at_t1"] != 0).sum()
            ),
            "clean_flow_intervals": int(
                (
                    (frozen_joint["trades_exactly_at_t1"] == 0)
                    & (frozen_joint["total_flow_qty"] > 0)
                ).sum()
            ),
            "signed_clean_intervals": int(
                (
                    (frozen_joint["trades_exactly_at_t1"] == 0)
                    & (frozen_joint["total_flow_qty"] > 0)
                    & (frozen_joint["signed_flow_qty"] != 0)
                ).sum()
            ),
        }

        for col, exp in expected.items():
            got = result[col]
            if isinstance(exp, float) and pd.isna(exp):
                match = pd.isna(got)
            else:
                match = got == exp
            ok = check(f"counter {hour}: {col}", bool(match),
                       f"got={got} exp={exp}") and ok

        # Gate: canonical replication gate must pass for every hour.
        gate_expected = bool(
            result["valid_bridges"] > 0
            and result["sequence_failures"] == 0
            and result["valid_event_records"] > 0
            and result["augmented_rows"] == result["d09_rows"]
            and result["touch_response_match"] == 1.0
        )
        ok = check(f"counter {hour}: gate_pass", result["gate_pass"] == gate_expected,
                   f"got={result['gate_pass']} exp={gate_expected}") and ok
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
            for hour, evt_df, aug_df, result in pool.imap_unordered(_process_one, todo):
                results[hour] = (evt_df, aug_df, result)
                with open(_checkpoint_path(hour), "wb") as f:
                    pickle.dump((evt_df, aug_df, result), f)
                print(f"  {hour}: {len(evt_df)} events, {len(aug_df)} joint rows")

    checks = [
        test_replication_events_exact(results),
        test_discovery_events_exact(results),
        test_replication_joint_exact(results),
        test_discovery_joint_exact(results),
        test_counters_match_frozen(results),
    ]
    n_pass = sum(checks)
    n_fail = len(checks) - n_pass
    print(f"\nRefactored D09B: {n_pass} passed, {n_fail} failed")
    return 0 if n_fail == 0 else 1


if __name__ == "__main__":
    sys.exit(main())