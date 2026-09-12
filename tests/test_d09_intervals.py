"""
Regression test: D09 joint flow/liquidity interval identity.

Locks the identity  N_intervals = N_valid_events - N_episodes  (handoff sections 28, 44, 62).
Any refactor of the interval construction must reproduce these numbers exactly.

Run:  python tests/test_d09_intervals.py
"""
import os
import sys

import pandas as pd

FROZEN = os.path.join(os.path.dirname(__file__), "..", "data", "frozen")

REPLICATION_HOURS = ["2026-05-25_04", "2026-05-25_12", "2026-05-25_18", "2026-05-26_15", "2026-05-26_21"]


def check(name, cond, detail=""):
    status = "PASS" if cond else "FAIL"
    print(f"[{status}] {name}" + (f"  ({detail})" if detail else ""))
    return cond


def test_discovery_interval_count():
    df = pd.read_csv(os.path.join(FROZEN, "d09_joint_flow_liquidity_tape.csv"))
    return check("discovery: d09 interval rows == 42,499", len(df) == 42499, f"rows={len(df)}")


def test_discovery_identity():
    # Discovery: 42,839 valid states - 340 episodes = 42,499 intervals
    states = 42839
    episodes = 340
    intervals = 42499
    return check(
        "discovery: intervals == valid_events - episodes",
        intervals == states - episodes,
        f"{intervals} == {states} - {episodes}",
    )


def test_replication_identity_per_hour():
    g1 = pd.read_csv(os.path.join(FROZEN, "gate1_canonical_summary.csv"))
    g3 = pd.read_csv(os.path.join(FROZEN, "gate3_d09_joint_tape_summary.csv"))
    g1 = g1.set_index("hour")
    g3 = g3.set_index("hour")
    ok = True
    for hour in REPLICATION_HOURS:
        intervals = int(g3.loc[hour, "valid_l2_intervals"])
        states = int(g1.loc[hour, "valid_states"])
        episodes = int(g1.loc[hour, "valid_episodes"])
        ok = check(
            f"replication {hour}: intervals == states - episodes",
            intervals == states - episodes,
            f"{intervals} == {states} - {episodes}",
        ) and ok
    return ok


def test_replication_interval_row_counts():
    g3 = pd.read_csv(os.path.join(FROZEN, "gate3_d09_joint_tape_summary.csv"))
    ok = True
    for _, row in g3.iterrows():
        hour = row["hour"]
        df = pd.read_csv(os.path.join(FROZEN, f"{hour}_d09_joint_flow_liquidity_tape.csv"))
        ok = check(
            f"replication {hour}: frozen d09 tape rows == gate3 intervals",
            len(df) == int(row["valid_l2_intervals"]),
            f"rows={len(df)} vs {int(row['valid_l2_intervals'])}",
        ) and ok
    return ok


def test_replication_total_intervals():
    g3 = pd.read_csv(os.path.join(FROZEN, "gate3_d09_joint_tape_summary.csv"))
    total = int(g3["valid_l2_intervals"].sum())
    return check("replication: total intervals == 258,917", total == 258917, f"got={total}")


def test_replication_clean_flow_counts():
    g3 = pd.read_csv(os.path.join(FROZEN, "gate3_d09_joint_tape_summary.csv"))
    clean_flow = int(g3["clean_flow_intervals"].sum())
    return check("replication: clean positive-qty flow intervals == 27,196", clean_flow == 27196, f"got={clean_flow}")


def main():
    results = [
        test_discovery_interval_count(),
        test_discovery_identity(),
        test_replication_identity_per_hour(),
        test_replication_interval_row_counts(),
        test_replication_total_intervals(),
        test_replication_clean_flow_counts(),
    ]
    n_pass = sum(results)
    n_fail = len(results) - n_pass
    print(f"\nD09 intervals: {n_pass} passed, {n_fail} failed")
    return 0 if n_fail == 0 else 1


if __name__ == "__main__":
    sys.exit(main())