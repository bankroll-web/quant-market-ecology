"""
Refactor validation: refactored D06 replay must reproduce frozen outputs exactly.

Runs src.book.replay.replay_hour on all six hours (discovery + 5 replication)
and compares:
  - per-hour states DataFrame vs frozen canonical_book_states CSV (exact,
    all columns)
  - discovery states vs frozen d06_reconstructed_book_states.csv (shared
    columns; discovery output has no hour/episode_id)
  - result counters vs frozen gate1_canonical_summary.csv

Frozen CSVs are read with float_precision='round_trip' so float columns
compare bit-for-bit (pandas' default C parser drops the last ULP).

Known artifact (documented in the research ledger): the discovery d06 run
summed top-5 depth with a naive loop (d06_replay_book.py), while the
replication gate1 run used sum() (compensated summation in Python 3.12+).
Verified: the frozen discovery depth columns equal the naive loop sum for
all 42,839 rows; sum() differs by up to 1.42e-14 in bid_depth_top5 /
ask_depth_top5 / obi_top5 only. This refactor follows the replication
canonical (sum()); the discovery comparison therefore allows a 1e-13
tolerance on those three columns and requires exact equality everywhere
else.

Runtime note: the canonical replay sorts the full book per state, so this
suite takes ~10-12 minutes serial (all six hours, replayed once each).
The harness replays the six independent hours across 3 worker processes,
cutting wall time to ~4-5 minutes. The refactored module itself is
unchanged by this; only the test harness parallelizes.

Each completed hour is checkpointed to tests/logs/checkpoints/d06/ so an
interrupted run resumes from where it left off instead of restarting.

Run:  python tests/test_refactored_d06.py
"""
import multiprocessing
import os
import pickle
import sys

import numpy as np
import pandas as pd
from pandas.testing import assert_frame_equal

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from src.book.replay import replay_hour  # noqa: E402

ROOT = os.path.join(os.path.dirname(__file__), "..")
FROZEN = os.path.join(ROOT, "data", "frozen")
RAW = os.path.join(ROOT, "data", "raw")
CHECKPOINT_DIR = os.path.join(ROOT, "tests", "logs", "checkpoints", "d06")

REPLICATION_HOURS = [
    "2026-05-25_04",
    "2026-05-25_12",
    "2026-05-25_18",
    "2026-05-26_15",
    "2026-05-26_21",
]
DISCOVERY_HOUR = "2026-05-25_00"

# Columns shared between refactored output and the discovery d06 output.
DISCOVERY_SHARED = [
    "received_time",
    "event_time",
    "event_kind",
    "local_update_id",
    "best_bid",
    "best_ask",
    "mid",
    "spread",
    "bid_levels",
    "ask_levels",
    "bid_depth_top5",
    "ask_depth_top5",
    "obi_top5",
    "crossed_book",
]

# gate1_canonical_summary.csv columns (states_file excluded).
SUMMARY_COLS = [
    "hour",
    "raw_rows",
    "snapshot_events",
    "update_events",
    "snapshots_loaded",
    "valid_snapshot_bridges",
    "invalid_snapshot_bridges",
    "stale_updates_skipped",
    "continuous_updates",
    "sequence_failures",
    "valid_states",
    "valid_episodes",
    "crossed_locked_states",
    "spread_mean",
    "spread_median",
    "spread_max",
    "gate1_pass",
]

# Columns affected by the discovery loop-vs-sum() depth artifact (1 ULP).
DEPTH_ULP_COLS = ["bid_depth_top5", "ask_depth_top5", "obi_top5"]


def read_frozen(name):
    return pd.read_csv(
        os.path.join(FROZEN, name),
        float_precision="round_trip",
    )


def check(name, cond, detail=""):
    status = "PASS" if cond else "FAIL"
    print(f"[{status}] {name}" + (f"  ({detail})" if detail else ""))
    return cond


def test_replication_states_exact(results):
    ok = True
    for hour in REPLICATION_HOURS:
        states_df = results[hour][0]
        frozen = read_frozen(f"{hour}_canonical_book_states.csv")
        try:
            assert_frame_equal(
                states_df.reset_index(drop=True),
                frozen.reset_index(drop=True),
                check_exact=True,
                check_dtype=True,
                obj=f"refactored vs frozen {hour}",
            )
            ok = check(f"replication {hour}: states DataFrame identical", True,
                       f"rows={len(states_df)}") and ok
        except AssertionError as exc:
            ok = check(f"replication {hour}: states DataFrame identical", False,
                       str(exc).splitlines()[0]) and ok
    return ok


def test_discovery_states_exact(results):
    states_df = results[DISCOVERY_HOUR][0]
    frozen = read_frozen("d06_reconstructed_book_states.csv")

    exact_cols = [c for c in DISCOVERY_SHARED if c not in DEPTH_ULP_COLS]
    try:
        assert_frame_equal(
            states_df[exact_cols].reset_index(drop=True),
            frozen[exact_cols].reset_index(drop=True),
            check_exact=True,
            check_dtype=True,
            obj="refactored vs frozen discovery d06 (exact cols)",
        )
    except AssertionError as exc:
        return check("discovery: states identical (all but depth cols)", False,
                     str(exc).splitlines()[0])

    ok = True
    for col in DEPTH_ULP_COLS:
        ref = states_df[col].to_numpy(dtype=float)
        exp = frozen[col].to_numpy(dtype=float)
        ok = check(
            f"discovery: {col} within naive-vs-sum tolerance",
            bool(np.allclose(ref, exp, rtol=1e-13, atol=1e-13, equal_nan=True)),
            f"max diff={np.abs(ref - exp)[~np.isnan(exp)].max():.3e}",
        ) and ok
    return ok


def test_summary_matches_gate1(results):
    g1 = read_frozen("gate1_canonical_summary.csv")
    ok = True
    for hour in REPLICATION_HOURS:
        result = results[hour][1]
        row = g1[g1["hour"] == hour].iloc[0]
        for col in SUMMARY_COLS:
            got = result[col]
            exp = row[col]
            if isinstance(exp, float) and pd.isna(exp):
                match = pd.isna(got)
            else:
                match = got == exp
            ok = check(f"summary {hour}: {col}", bool(match), f"got={got} exp={exp}") and ok
    return ok


def _checkpoint_path(hour):
    return os.path.join(CHECKPOINT_DIR, f"{hour}.pkl")


def _replay_one(hour):
    """Top-level worker (picklable under Windows spawn)."""
    states_df, result = replay_hour(hour, RAW)
    return hour, states_df, result


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
        print(f"Replaying {len(todo)} hours (3 parallel workers)...")
        with multiprocessing.Pool(processes=3) as pool:
            for hour, states_df, result in pool.imap_unordered(_replay_one, todo):
                results[hour] = (states_df, result)
                with open(_checkpoint_path(hour), "wb") as f:
                    pickle.dump((states_df, result), f)
                print(f"  {hour}: {len(states_df)} states")

    checks = [
        test_replication_states_exact(results),
        test_discovery_states_exact(results),
        test_summary_matches_gate1(results),
    ]
    n_pass = sum(checks)
    n_fail = len(checks) - n_pass
    print(f"\nRefactored D06: {n_pass} passed, {n_fail} failed")
    return 0 if n_fail == 0 else 1


if __name__ == "__main__":
    sys.exit(main())