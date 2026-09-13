"""
Refactor validation: refactored EXP-01 analysis layer must reproduce
frozen outputs exactly.

Runs src.analysis.exp01 on the frozen d09b joint CSVs (read with the
DEFAULT parser, matching the canonical input per ledger O9) and compares:
  - exp01c: analysis frame + group summary (discovery)
  - exp01d: episode-level cluster bootstrap (checkpointed); input is the
    written exp01c_canonical_rows.csv read with the DEFAULT parser,
    exactly as the canonical exp01d reads it
  - exp01e: equal-weight episode effects + summary (discovery); same
    CSV-read input note as exp01d
  - replication: canonical rows, per-hour summary, equal-episode
    effects + final summary (5 hours)

Frozen outputs are read with float_precision='round_trip' (O7).

Runtime: first run ~2-5 min (exp01d bootstrap, checkpointed); instant
on re-run.

Run:  python tests/test_refactored_exp01.py
"""
import os
import pickle
import sys

import pandas as pd
from pandas.testing import assert_frame_equal

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from src.analysis.exp01 import (  # noqa: E402
    build_analysis_frame,
    build_replication_rows,
    episode_bootstrap,
    equal_episode_effects,
    equal_episode_summary,
    group_summary,
    per_hour_summary,
)

ROOT = os.path.join(os.path.dirname(__file__), "..")
FROZEN = os.path.join(ROOT, "data", "frozen")
CHECKPOINT_DIR = os.path.join(ROOT, "tests", "logs", "checkpoints", "exp01")

REPLICATION_HOURS = [
    "2026-05-25_04",
    "2026-05-25_12",
    "2026-05-25_18",
    "2026-05-26_15",
    "2026-05-26_21",
]


def read_frozen(name):
    return pd.read_csv(
        os.path.join(FROZEN, name),
        float_precision="round_trip",
    )


def read_input(name):
    """Canonical input read: DEFAULT parser (O9)."""
    return pd.read_csv(os.path.join(FROZEN, name))


def check(name, cond, detail=""):
    status = "PASS" if cond else "FAIL"
    print(f"[{status}] {name}" + (f"  ({detail})" if detail else ""))
    return cond


def _compare(got, frozen, label):
    try:
        assert_frame_equal(
            got.reset_index(drop=True),
            frozen.reset_index(drop=True),
            check_exact=True,
            check_dtype=True,
            obj=label,
        )
        return check(label, True, f"rows={len(got)}")
    except AssertionError as exc:
        return check(label, False, str(exc).splitlines()[0])


# ---------------------------------------------------------------------
# exp01c: discovery analysis frame + group summary
# ---------------------------------------------------------------------

def test_exp01c_rows(x):
    frozen = read_frozen("exp01c_canonical_rows.csv")
    return _compare(x, frozen, "exp01c: canonical rows identical")


def test_exp01c_summary(x):
    summary = group_summary(x)
    frozen = read_frozen("exp01c_canonical_summary.csv")
    return _compare(summary, frozen, "exp01c: group summary identical")


# ---------------------------------------------------------------------
# exp01d: episode-level cluster bootstrap (checkpointed)
#
# Canonical exp01d reads the WRITTEN exp01c_canonical_rows.csv with the
# DEFAULT parser (not the in-memory frame): the written CSV round-trips
# through default-parser last-ULP artifacts (O9), so the bootstrap input
# must be the CSV-read frame to reproduce the frozen output bit-for-bit.
# ---------------------------------------------------------------------

def _bootstrap_checkpoint_path():
    return os.path.join(CHECKPOINT_DIR, "episode_bootstrap.pkl")


def test_exp01d_bootstrap():
    cp = _bootstrap_checkpoint_path()
    if os.path.exists(cp):
        with open(cp, "rb") as f:
            result = pickle.load(f)
        print("  exp01d: loaded from checkpoint")
    else:
        print("  exp01d: running 10000-draw episode bootstrap...")
        result = episode_bootstrap(
            read_input("exp01c_canonical_rows.csv")
        )
        os.makedirs(CHECKPOINT_DIR, exist_ok=True)
        with open(cp, "wb") as f:
            pickle.dump(result, f)
    frozen = read_frozen("exp01d_episode_bootstrap.csv")
    return _compare(result, frozen, "exp01d: episode bootstrap identical")


# ---------------------------------------------------------------------
# exp01e: equal-weight episode test (discovery)
#
# Same input note as exp01d: canonical exp01e reads the written
# exp01c_canonical_rows.csv with the DEFAULT parser.
# ---------------------------------------------------------------------

def test_exp01e():
    x = read_input("exp01c_canonical_rows.csv")
    effects = equal_episode_effects(x, "episode_id")
    summary = equal_episode_summary(effects, "episode_id")
    ok = _compare(
        effects,
        read_frozen("exp01e_equal_episode_effects.csv"),
        "exp01e: episode effects identical",
    )
    ok = _compare(
        summary,
        read_frozen("exp01e_equal_episode_summary.csv"),
        "exp01e: equal-episode summary identical",
    ) and ok
    return ok


# ---------------------------------------------------------------------
# replication: canonical rows + per-hour + equal-episode
# ---------------------------------------------------------------------

def test_replication_rows(rows):
    frozen = read_frozen("exp01_replication_canonical_rows.csv")
    return _compare(rows, frozen, "replication: canonical rows identical")


def test_replication_hour_summary(rows):
    hour_summary = per_hour_summary(rows, REPLICATION_HOURS)
    frozen = read_frozen("exp01_replication_hour_summary.csv")
    return _compare(hour_summary, frozen, "replication: hour summary identical")


def test_replication_equal_episode(rows):
    effects = equal_episode_effects(rows, "global_episode_id")
    summary = equal_episode_summary(
        effects, "global_episode_id", include_concentration=True
    )
    ok = _compare(
        effects,
        read_frozen("exp01_replication_equal_episode_effects.csv"),
        "replication: equal-episode effects identical",
    )
    ok = _compare(
        summary,
        read_frozen("exp01_replication_final_summary.csv"),
        "replication: final summary identical",
    ) and ok
    return ok


def main():
    # Discovery analysis frame (shared by exp01c/d/e).
    print("Building discovery analysis frame...")
    x = build_analysis_frame(
        read_input("d09b_joint_flow_touch_ecology.csv")
    )
    print(f"  starting events: {len(x):,}")

    # Replication rows (shared by all replication tests).
    print("Building replication rows (5 hours)...")
    hour_dfs = {
        hour: read_input(f"{hour}_d09b_joint_flow_touch_ecology.csv")
        for hour in REPLICATION_HOURS
    }
    rows = build_replication_rows(hour_dfs)
    print(f"  combined starting events: {len(rows):,}")

    checks = [
        test_exp01c_rows(x),
        test_exp01c_summary(x),
        test_exp01d_bootstrap(),
        test_exp01e(),
        test_replication_rows(rows),
        test_replication_hour_summary(rows),
        test_replication_equal_episode(rows),
    ]
    n_pass = sum(checks)
    n_fail = len(checks) - n_pass
    print(f"\nRefactored EXP-01: {n_pass} passed, {n_fail} failed")
    return 0 if n_fail == 0 else 1


if __name__ == "__main__":
    sys.exit(main())