"""
Regression test: D06 verified order-book reconstruction.

Locks the canonical D06 sequence state machine outputs (handoff sections 22-23, 40).
Any refactor of the reconstruction logic must reproduce these numbers exactly.

Run:  python tests/test_d06_reconstruction.py
"""
import os
import sys

import pandas as pd

FROZEN = os.path.join(os.path.dirname(__file__), "..", "data", "frozen")

# Recorded discovery counts (handoff section 22) - printed by d06_replay_book.py
DISCOVERY_EXPECTED = {
    "snapshots": 729,
    "valid_snapshot_bridges": 340,
    "invalid_bridges": 24,
    "stale_updates": 918,
    "continuous_updates": 42499,
    "sequence_failures": 0,
    "valid_states": 42839,
    "crossed_locked_states": 0,
}

# Recorded per-hour replication counts (handoff section 40 / gate1_canonical_summary.csv)
REPLICATION_EXPECTED = {
    "2026-05-25_04": {"valid_bridges": 122, "invalid": 13, "stale": 307, "continuous": 23627, "failures": 0, "states": 23749, "episodes": 122},
    "2026-05-25_12": {"valid_bridges": 234, "invalid": 8, "stale": 645, "continuous": 55577, "failures": 0, "states": 55811, "episodes": 234},
    "2026-05-25_18": {"valid_bridges": 103, "invalid": 3, "stale": 295, "continuous": 57396, "failures": 0, "states": 57499, "episodes": 103},
    "2026-05-26_15": {"valid_bridges": 215, "invalid": 7, "stale": 718, "continuous": 50852, "failures": 0, "states": 51067, "episodes": 215},
    "2026-05-26_21": {"valid_bridges": 143, "invalid": 8, "stale": 389, "continuous": 71465, "failures": 0, "states": 71608, "episodes": 143},
}


def check(name, cond, detail=""):
    status = "PASS" if cond else "FAIL"
    print(f"[{status}] {name}" + (f"  ({detail})" if detail else ""))
    return cond


def test_discovery_book_states_row_count():
    df = pd.read_csv(os.path.join(FROZEN, "d06_reconstructed_book_states.csv"))
    return check(
        "discovery: d06_reconstructed_book_states.csv rows == 42,839",
        len(df) == DISCOVERY_EXPECTED["valid_states"],
        f"rows={len(df)}",
    )


def test_discovery_book_state_columns():
    df = pd.read_csv(os.path.join(FROZEN, "d06_reconstructed_book_states.csv"))
    required = ["best_bid", "best_ask", "mid", "spread", "bid_depth_top5", "ask_depth_top5", "obi_top5", "crossed_book"]
    missing = [c for c in required if c not in df.columns]
    return check("discovery: book-state schema complete", not missing, f"missing={missing}")


def test_discovery_no_crossed_books():
    df = pd.read_csv(os.path.join(FROZEN, "d06_reconstructed_book_states.csv"))
    n_crossed = int((df["crossed_book"] != 0).sum())
    return check(
        "discovery: crossed/locked states == 0",
        n_crossed == DISCOVERY_EXPECTED["crossed_locked_states"],
        f"crossed={n_crossed}",
    )


def test_replication_gate1_counts():
    g1 = pd.read_csv(os.path.join(FROZEN, "gate1_canonical_summary.csv"))
    ok = True
    for _, row in g1.iterrows():
        hour = row["hour"]
        exp = REPLICATION_EXPECTED[hour]
        checks = {
            "valid_bridges": row["valid_snapshot_bridges"] == exp["valid_bridges"],
            "invalid_bridges": row["invalid_snapshot_bridges"] == exp["invalid"],
            "stale_updates": row["stale_updates_skipped"] == exp["stale"],
            "continuous_updates": row["continuous_updates"] == exp["continuous"],
            "sequence_failures": row["sequence_failures"] == exp["failures"],
            "valid_states": row["valid_states"] == exp["states"],
            "valid_episodes": row["valid_episodes"] == exp["episodes"],
            "gate1_pass": bool(row["gate1_pass"]),
        }
        for name, c in checks.items():
            ok = check(f"replication {hour}: {name}", c, f"got={row[name] if name in row else ''}") and ok
    return ok


def test_replication_totals():
    g1 = pd.read_csv(os.path.join(FROZEN, "gate1_canonical_summary.csv"))
    totals = {
        "episodes": int(g1["valid_episodes"].sum()),
        "states": int(g1["valid_states"].sum()),
        "continuous": int(g1["continuous_updates"].sum()),
        "invalid": int(g1["invalid_snapshot_bridges"].sum()),
        "stale": int(g1["stale_updates_skipped"].sum()),
        "failures": int(g1["sequence_failures"].sum()),
    }
    expected = {"episodes": 817, "states": 259734, "continuous": 258917, "invalid": 39, "stale": 2354, "failures": 0}
    ok = True
    for k, v in expected.items():
        ok = check(f"replication totals: {k} == {v}", totals[k] == v, f"got={totals[k]}") and ok
    return ok


def main():
    results = [
        test_discovery_book_states_row_count(),
        test_discovery_book_state_columns(),
        test_discovery_no_crossed_books(),
        test_replication_gate1_counts(),
        test_replication_totals(),
    ]
    n_pass = sum(results)
    n_fail = len(results) - n_pass
    print(f"\nD06 reconstruction: {n_pass} passed, {n_fail} failed")
    return 0 if n_fail == 0 else 1


if __name__ == "__main__":
    sys.exit(main())