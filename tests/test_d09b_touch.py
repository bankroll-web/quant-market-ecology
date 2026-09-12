"""
Regression test: D09B spatial liquidity (touch-distance) ecology.

Locks the touch-distance classification layer (handoff sections 29, 45, 62):
- per-hour d09b joint flow touch ecology must match d09 interval counts exactly
- discovery d09b outputs must match d06/d09 counts exactly
- bucket identity: net = add - remove within each distance band

Run:  python tests/test_d09b_touch.py
"""
import os
import sys

import pandas as pd

FROZEN = os.path.join(os.path.dirname(__file__), "..", "data", "frozen")

REPLICATION_HOURS = ["2026-05-25_04", "2026-05-25_12", "2026-05-25_18", "2026-05-26_15", "2026-05-26_21"]

BUCKET_PAIRS = [
    ("bid_net_0_5_qty", "bid_add_0_5_qty", "bid_remove_0_5_qty"),
    ("bid_net_6_20_qty", "bid_add_6_20_qty", "bid_remove_6_20_qty"),
    ("bid_net_gt20_qty", "bid_add_gt20_qty", "bid_remove_gt20_qty"),
    ("ask_net_0_5_qty", "ask_add_0_5_qty", "ask_remove_0_5_qty"),
    ("ask_net_6_20_qty", "ask_add_6_20_qty", "ask_remove_6_20_qty"),
    ("ask_net_gt20_qty", "ask_add_gt20_qty", "ask_remove_gt20_qty"),
]


def check(name, cond, detail=""):
    status = "PASS" if cond else "FAIL"
    print(f"[{status}] {name}" + (f"  ({detail})" if detail else ""))
    return cond


def test_discovery_touch_ecology_count():
    df = pd.read_csv(os.path.join(FROZEN, "d09b_joint_flow_touch_ecology.csv"))
    return check("discovery: d09b touch ecology rows == 42,499", len(df) == 42499, f"rows={len(df)}")


def test_discovery_touch_book_events_count():
    df = pd.read_csv(os.path.join(FROZEN, "d09b_touch_distance_book_events.csv"))
    return check("discovery: d09b book events rows == 42,839", len(df) == 42839, f"rows={len(df)}")


def test_discovery_touch_ecology_matches_d09():
    eco = pd.read_csv(os.path.join(FROZEN, "d09b_joint_flow_touch_ecology.csv"))
    d09 = pd.read_csv(os.path.join(FROZEN, "d09_joint_flow_liquidity_tape.csv"))
    same_keys = (eco["episode_id"] == d09["episode_id"]).all() and (eco["interval_index"] == d09["interval_index"]).all()
    return check("discovery: d09b ecology keys == d09 keys", same_keys)


def test_replication_touch_ecology_matches_d09():
    ok = True
    for hour in REPLICATION_HOURS:
        eco = pd.read_csv(os.path.join(FROZEN, f"{hour}_d09b_joint_flow_touch_ecology.csv"))
        d09 = pd.read_csv(os.path.join(FROZEN, f"{hour}_d09_joint_flow_liquidity_tape.csv"))
        same_keys = (eco["episode_id"] == d09["episode_id"]).all() and (eco["interval_index"] == d09["interval_index"]).all()
        ok = check(
            f"replication {hour}: d09b ecology keys == d09 keys",
            same_keys,
            f"rows={len(eco)}",
        ) and ok
    return ok


def test_bucket_net_identity():
    df = pd.read_csv(os.path.join(FROZEN, "d09b_touch_distance_book_events.csv"))
    ok = True
    for net_col, add_col, rem_col in BUCKET_PAIRS:
        mismatch = int((df[net_col] - (df[add_col] - df[rem_col])).abs().sum())
        ok = check(
            f"bucket identity: {net_col} == {add_col} - {rem_col}",
            mismatch == 0,
            f"abs mismatch sum={mismatch}",
        ) and ok
    return ok


def test_tick_bucket_columns_present():
    df = pd.read_csv(os.path.join(FROZEN, "d09b_touch_distance_book_events.csv"))
    required = ["best_bid_before", "best_ask_before", "mid_before", "mid_after"]
    missing = [c for c in required if c not in df.columns]
    return check("d09b book events: pre-event touch columns present", not missing, f"missing={missing}")


def main():
    results = [
        test_discovery_touch_ecology_count(),
        test_discovery_touch_book_events_count(),
        test_discovery_touch_ecology_matches_d09(),
        test_replication_touch_ecology_matches_d09(),
        test_bucket_net_identity(),
        test_tick_bucket_columns_present(),
    ]
    n_pass = sum(results)
    n_fail = len(results) - n_pass
    print(f"\nD09B touch ecology: {n_pass} passed, {n_fail} failed")
    return 0 if n_fail == 0 else 1


if __name__ == "__main__":
    sys.exit(main())