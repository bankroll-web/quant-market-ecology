"""
D09 provenance validation gate (PE-3A follow-up, review-approved).

Validates the additive D09 provenance field latest_trade_received_time_ns
against the review gate:

  A. canonical interval membership unchanged
  B. provenance == max(raw received_time_ns of canonical contributing
     trades) over the exact (t0, t1] slice
  C. no-trade intervals carry explicit missing provenance
  D. exact-t1 trades remain included/excluded exactly as frozen
  E. all pre-existing D09 columns reproduce bit-for-bit
  F. D09B carries the new field without changing any existing column
  G. EXP-01 frozen outputs remain bit-for-bit identical
  H. all existing suites remain green (run_tests.py)

Missing representation: the field is int64 with sentinel 0 for no-trade
intervals. NaN cannot be used: received_time_ns ~1.75e18 exceeds 2^53, so
float64 (the only dtype pandas can produce for a NaN-mixed column) would
corrupt the provenance by ~128 ns, and the default-parser CSV round-trip
(O11) could not preserve the exactness gate B requires. Sentinel 0 is
explicit missing provenance: never carried forward, never substituted
with the t1 book receipt, never fabricated.

D09 checkpoints are SHARED with test_refactored_d09.py (same build, same
format); stale pre-provenance checkpoints are detected by the missing
column and rebuilt. D09B joints are built from the REBUILT D09 CSVs
(written to tests/logs/tmp, read back with the DEFAULT parser per O11)
and checkpointed separately.

Runtime: first run ~15-25 min (D09 + D09B builds, parallel 3 workers,
checkpointed); instant on re-run.

Run:  python tests/test_d09_provenance.py
"""
import multiprocessing
import os
import pickle
import sys

import numpy as np
import pandas as pd
from pandas.testing import assert_frame_equal

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from src.analysis.exp01 import (  # noqa: E402
    build_analysis_frame,
    build_replication_rows,
)
from src.ingestion.cryptohft import read_cryptohft  # noqa: E402
from src.liquidity.joint_flow import process_hour as d09_process_hour  # noqa: E402
from src.liquidity.touch_ecology import process_hour as d09b_process_hour  # noqa: E402

ROOT = os.path.join(os.path.dirname(__file__), "..")
FROZEN = os.path.join(ROOT, "data", "frozen")
RAW = os.path.join(ROOT, "data", "raw")
D09_CHECKPOINT_DIR = os.path.join(ROOT, "tests", "logs", "checkpoints", "d09")
JOINT_CHECKPOINT_DIR = os.path.join(
    ROOT, "tests", "logs", "checkpoints", "d09_provenance"
)
TMP_DIR = os.path.join(ROOT, "tests", "logs", "tmp", "d09_provenance")

REPLICATION_HOURS = [
    "2026-05-25_04",
    "2026-05-25_12",
    "2026-05-25_18",
    "2026-05-26_15",
    "2026-05-26_21",
]
DISCOVERY_HOUR = "2026-05-25_00"
HOURS = [DISCOVERY_HOUR] + REPLICATION_HOURS

UTC_COLS = ["t0_utc", "t1_utc"]
JOINT_UTC_COLS = ["t0_utc", "t1_utc"]


def read_frozen(name):
    return pd.read_csv(
        os.path.join(FROZEN, name),
        float_precision="round_trip",
    )


def normalize_utc(df, cols=UTC_COLS):
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


# ---------------------------------------------------------------------
# D09 build (shared checkpoints with test_refactored_d09.py)
# ---------------------------------------------------------------------

def _book_csv(hour):
    if hour == DISCOVERY_HOUR:
        return os.path.join(FROZEN, "d07_liquidity_event_tape.csv")
    return os.path.join(FROZEN, f"{hour}_d07_liquidity_event_tape.csv")


def _build_d09_one(hour):
    """Top-level worker (picklable under Windows spawn)."""
    records_df, result = d09_process_hour(hour, _book_csv(hour), RAW)
    return hour, records_df, result


def _ensure_d09():
    """Load D09 from the shared checkpoint dir, building missing/stale."""
    results = {}
    todo = []
    for hour in HOURS:
        cp = os.path.join(D09_CHECKPOINT_DIR, f"{hour}.pkl")
        if os.path.exists(cp):
            with open(cp, "rb") as f:
                records_df, result = pickle.load(f)
            if "latest_trade_received_time_ns" in records_df.columns:
                results[hour] = (records_df, result)
                continue
        todo.append(hour)
    if todo:
        print(f"  building D09 for {len(todo)} hour(s)...")
        with multiprocessing.Pool(3) as pool:
            for hour, records_df, result in pool.imap_unordered(
                _build_d09_one, todo
            ):
                with open(
                    os.path.join(D09_CHECKPOINT_DIR, f"{hour}.pkl"), "wb"
                ) as f:
                    pickle.dump((records_df, result), f)
                results[hour] = (records_df, result)
    return results


# ---------------------------------------------------------------------
# D09B joint build from the REBUILT D09 CSVs (gate F/G input)
# ---------------------------------------------------------------------

def _build_joint_one(hour):
    """Top-level worker (picklable under Windows spawn)."""
    with open(os.path.join(D09_CHECKPOINT_DIR, f"{hour}.pkl"), "rb") as f:
        records_df, _ = pickle.load(f)
    tmp_csv = os.path.join(TMP_DIR, f"{hour}_d09_provenance.csv")
    records_df.to_csv(tmp_csv, index=False)
    evt_df, aug_df, result = d09b_process_hour(hour, RAW, tmp_csv)
    return hour, aug_df, result


def _ensure_joints():
    """Load D09B joints built from the rebuilt D09 CSVs (checkpointed)."""
    results = {}
    todo = []
    for hour in HOURS:
        cp = os.path.join(JOINT_CHECKPOINT_DIR, f"{hour}.pkl")
        if os.path.exists(cp):
            with open(cp, "rb") as f:
                aug_df, result = pickle.load(f)
            if "latest_trade_received_time_ns" in aug_df.columns:
                results[hour] = (aug_df, result)
                continue
        todo.append(hour)
    if todo:
        print(f"  building D09B joints for {len(todo)} hour(s)...")
        with multiprocessing.Pool(3) as pool:
            for hour, aug_df, result in pool.imap_unordered(
                _build_joint_one, todo
            ):
                with open(
                    os.path.join(JOINT_CHECKPOINT_DIR, f"{hour}.pkl"), "wb"
                ) as f:
                    pickle.dump((aug_df, result), f)
                results[hour] = (aug_df, result)
    return results


# ---------------------------------------------------------------------
# Independent provenance recomputation (gate B)
# ---------------------------------------------------------------------

def _recompute_latest_trade_received(records_df, trades):
    """max(raw received_time_ns) over the canonical (t0, t1] slice.

    right/right searchsorted on trade_time_ms, sentinel 0 when the slice
    is empty. Membership is identical to the canonical per-episode slice
    because ep_start <= t0 < t1 <= ep_end.
    """
    trades = trades.copy()
    trades["trade_time_ms"] = pd.to_numeric(
        trades["trade_time"], errors="raise"
    ).astype("int64")
    trades["received_time_ns"] = pd.to_numeric(
        trades["received_time"], errors="raise"
    ).astype("int64")
    trades = trades.sort_values(
        ["trade_time_ms", "trade_id"]
    ).reset_index(drop=True)
    tt = trades["trade_time_ms"].to_numpy(dtype=np.int64)
    rt = trades["received_time_ns"].to_numpy(dtype=np.int64)
    t0 = records_df["t0_event_time_ms"].to_numpy(dtype=np.int64)
    t1 = records_df["t1_event_time_ms"].to_numpy(dtype=np.int64)
    left = np.searchsorted(tt, t0, side="right")
    right = np.searchsorted(tt, t1, side="right")
    out = np.zeros(len(records_df), dtype=np.int64)
    for i in range(len(records_df)):
        if right[i] > left[i]:
            out[i] = int(rt[left[i]:right[i]].max())
    return out


# ---------------------------------------------------------------------
# Gates
# ---------------------------------------------------------------------

def test_gate_a(records, frozen):
    ok = True
    for hour in HOURS:
        r = records[hour][0]
        f = frozen[hour]
        keys = ["episode_id", "t0_event_time_ms", "t1_event_time_ms"]
        same_len = len(r) == len(f)
        same_keys = bool(
            (r[keys].to_numpy() == f[keys].to_numpy()).all()
        )
        ok = check(
            f"A {hour}: canonical interval membership unchanged",
            same_len and same_keys,
            f"rows={len(r)}",
        ) and ok
    return ok


def test_gate_b(records):
    ok = True
    for hour in HOURS:
        r = records[hour][0]
        trades = read_cryptohft(
            os.path.join(RAW, f"BTCUSDT_trades_{hour}.parquet")
        )
        recomputed = _recompute_latest_trade_received(r, trades)
        del trades
        built = r["latest_trade_received_time_ns"].to_numpy(dtype=np.int64)
        match = bool((built == recomputed).all())
        n_trade = int((r["n_trades"] > 0).sum())
        ok = check(
            f"B {hour}: provenance == max(raw received_time, canonical slice)",
            match,
            f"trade intervals={n_trade}",
        ) and ok
    return ok


def test_gate_c(records):
    ok = True
    for hour in HOURS:
        r = records[hour][0]
        no_trade = r["n_trades"] == 0
        with_trade = r["n_trades"] > 0
        c1 = bool((r.loc[no_trade, "latest_trade_received_time_ns"] == 0).all())
        c2 = bool((r.loc[with_trade, "latest_trade_received_time_ns"] > 0).all())
        ok = check(
            f"C {hour}: no-trade intervals explicit missing (sentinel 0)",
            c1 and c2,
            f"no-trade={int(no_trade.sum())}",
        ) and ok
    return ok


def test_gate_d(records, frozen):
    ok = True
    for hour in HOURS:
        r = records[hour][0]
        f = frozen[hour]
        same = bool(
            (
                r["trades_exactly_at_t1"].to_numpy()
                == f["trades_exactly_at_t1"].to_numpy()
            ).all()
        )
        ok = check(
            f"D {hour}: exact-t1 trades included/excluded as frozen",
            same,
        ) and ok
    return ok


def test_gate_e(records, frozen):
    ok = True
    for hour in HOURS:
        r = normalize_utc(records[hour][0])
        f = normalize_utc(frozen[hour])
        try:
            assert_frame_equal(
                r[f.columns].reset_index(drop=True),
                f.reset_index(drop=True),
                check_exact=True,
                check_dtype=True,
                obj=f"gate E {hour} d09 frozen columns",
            )
            ok = check(
                f"E {hour}: pre-existing D09 columns bit-for-bit", True
            ) and ok
        except AssertionError as exc:
            ok = check(
                f"E {hour}: pre-existing D09 columns bit-for-bit", False,
                str(exc).splitlines()[0],
            ) and ok
    return ok


def test_gate_f(joints, frozen_joints):
    ok = True
    for hour in HOURS:
        aug = joints[hour][0]
        f = normalize_utc(frozen_joints[hour], JOINT_UTC_COLS)
        aug_n = normalize_utc(aug, JOINT_UTC_COLS)
        has_col = "latest_trade_received_time_ns" in aug.columns
        try:
            assert_frame_equal(
                aug_n[f.columns].reset_index(drop=True),
                f.reset_index(drop=True),
                check_exact=True,
                check_dtype=True,
                obj=f"gate F {hour} d09b joint frozen columns",
            )
            ok = check(
                f"F {hour}: D09B carries field, existing columns unchanged",
                has_col,
                f"rows={len(aug)}",
            ) and ok
        except AssertionError as exc:
            ok = check(
                f"F {hour}: D09B carries field, existing columns unchanged",
                False,
                str(exc).splitlines()[0],
            ) and ok
    return ok


def test_gate_g(joints):
    ok = True
    # exp01c: discovery analysis frame on the rebuilt D09B joint.
    x = build_analysis_frame(joints[DISCOVERY_HOUR][0])
    frozen_c = read_frozen("exp01c_canonical_rows.csv")
    try:
        assert_frame_equal(
            x[frozen_c.columns].reset_index(drop=True),
            frozen_c.reset_index(drop=True),
            check_exact=True,
            check_dtype=True,
            obj="gate G exp01c canonical rows",
        )
        ok = check(
            "G: exp01c canonical rows bit-for-bit (rebuilt D09B input)",
            True,
            f"rows={len(x)}",
        ) and ok
    except AssertionError as exc:
        ok = check(
            "G: exp01c canonical rows bit-for-bit (rebuilt D09B input)",
            False,
            str(exc).splitlines()[0],
        ) and ok
    # Replication canonical rows on the rebuilt D09B joints.
    hour_dfs = {hour: joints[hour][0] for hour in REPLICATION_HOURS}
    rows = build_replication_rows(hour_dfs)
    frozen_r = read_frozen("exp01_replication_canonical_rows.csv")
    try:
        assert_frame_equal(
            rows[frozen_r.columns].reset_index(drop=True),
            frozen_r.reset_index(drop=True),
            check_exact=True,
            check_dtype=True,
            obj="gate G replication canonical rows",
        )
        ok = check(
            "G: replication canonical rows bit-for-bit (rebuilt D09B input)",
            True,
            f"rows={len(rows)}",
        ) and ok
    except AssertionError as exc:
        ok = check(
            "G: replication canonical rows bit-for-bit (rebuilt D09B input)",
            False,
            str(exc).splitlines()[0],
        ) and ok
    return ok


def main():
    os.makedirs(D09_CHECKPOINT_DIR, exist_ok=True)
    os.makedirs(JOINT_CHECKPOINT_DIR, exist_ok=True)
    os.makedirs(TMP_DIR, exist_ok=True)

    print("Loading/building D09 (shared checkpoints)...")
    records = _ensure_d09()
    print("Loading/building D09B joints from rebuilt D09 CSVs...")
    joints = _ensure_joints()

    frozen = {
        hour: read_frozen(f"{hour}_d09_joint_flow_liquidity_tape.csv")
        for hour in REPLICATION_HOURS
    }
    frozen[DISCOVERY_HOUR] = read_frozen("d09_joint_flow_liquidity_tape.csv")
    frozen_joints = {
        hour: read_frozen(f"{hour}_d09b_joint_flow_touch_ecology.csv")
        for hour in REPLICATION_HOURS
    }
    frozen_joints[DISCOVERY_HOUR] = read_frozen(
        "d09b_joint_flow_touch_ecology.csv"
    )

    checks = [
        test_gate_a(records, frozen),
        test_gate_b(records),
        test_gate_c(records),
        test_gate_d(records, frozen),
        test_gate_e(records, frozen),
        test_gate_f(joints, frozen_joints),
        test_gate_g(joints),
    ]
    n_pass = sum(checks)
    n_fail = len(checks) - n_pass
    print(f"\nD09 provenance gate: {n_pass} passed, {n_fail} failed")
    return 0 if n_fail == 0 else 1


if __name__ == "__main__":
    sys.exit(main())