"""
PE-2 test gate: frozen EXP-01 signal-state reconstruction.

Gate A (frozen field equality vs canonical add_flow_state), B (eligibility
counts, per-hour + aggregate), C (side semantics), D (response semantics),
E (no lookahead), F (episode-first behavior), G (determinism),
H (input immutability). Gate I (upstream regression) is run_tests.py
itself (12 suites after this file is added).

Runs on all six validated hours, one hour at a time (serial, per-hour
memory discipline, ledger O10). Tapes are read with the DEFAULT parser
(ledger O11). Canonical reference: the full exp01c pipeline
src/analysis/exp01.py build_analysis_frame (prepare_intervals +
add_flow_state) applied to the D09B frame; it defines flow-state values
exactly for the eligible (firewall-passing) rows, and gate A compares
every eligible event bit-for-bit / NaN-aware against it.

Run:  python tests/test_paper_engine_signal.py
"""
import os
import sys
import warnings

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from src.analysis.exp01 import build_analysis_frame  # noqa: E402
from src.paper_engine.signal import (  # noqa: E402
    SIGNAL_INPUT_FIELDS,
    DIRECTION_COMPARATOR,
    DIRECTION_LONG,
    DIRECTION_NEUTRAL,
    DIRECTION_SHORT,
    RESPONSE_DEPLETION,
    RESPONSE_NEUTRAL,
    RESPONSE_REPLENISHMENT,
    iter_signals,
    signal_from_state,
)
from src.paper_engine.state import iter_states  # noqa: E402

ROOT = os.path.join(os.path.dirname(__file__), "..")
FROZEN = os.path.join(ROOT, "data", "frozen")

REPLICATION_HOURS = [
    "2026-05-25_04",
    "2026-05-25_12",
    "2026-05-25_18",
    "2026-05-26_15",
    "2026-05-26_21",
]
DISCOVERY_HOUR = "2026-05-25_00"
HOURS = [DISCOVERY_HOUR] + REPLICATION_HOURS

# Frozen eligible starting-event counts (exp01c / exp01 replication).
ELIGIBLE_EXPECTED = {
    "2026-05-25_00": 3733,
    "2026-05-25_04": 1652,
    "2026-05-25_12": 4753,
    "2026-05-25_18": 3059,
    "2026-05-26_15": 12708,
    "2026-05-26_21": 4965,
}
ELIGIBLE_TOTAL = 30870  # 3,733 discovery + 27,137 replication

# Frozen response-class counts among ELIGIBLE events (exp01c / replication).
RESPONSE_EXPECTED = {
    "2026-05-25_00": {"DEPLETION": 3254, "REPLENISHMENT": 439, "NEUTRAL": 40},
    "replication": {"DEPLETION": 22775, "REPLENISHMENT": 4093, "NEUTRAL": 269},
}


def check(name, cond, detail=""):
    status = "PASS" if cond else "FAIL"
    print(f"[{status}] {name}" + (f"  ({detail})" if detail else ""))
    return cond


def _tapes(hour):
    if hour == DISCOVERY_HOUR:
        d07 = pd.read_csv(os.path.join(FROZEN, "d07_liquidity_event_tape.csv"))
        d09 = pd.read_csv(os.path.join(FROZEN, "d09b_joint_flow_touch_ecology.csv"))
    else:
        d07 = pd.read_csv(
            os.path.join(FROZEN, f"{hour}_d07_liquidity_event_tape.csv")
        )
        d09 = pd.read_csv(
            os.path.join(FROZEN, f"{hour}_d09b_joint_flow_touch_ecology.csv")
        )
    return d07, d09


def _same_float(a, b):
    if isinstance(a, float) and isinstance(b, float):
        if pd.isna(a) and pd.isna(b):
            return True
    return a == b


def _same_dict(da, db):
    if da is None or db is None:
        return da is db
    if set(da) != set(db):
        return False
    return all(_same_float(da[k], db[k]) for k in da)


# ----------------------------------------------------------------- gate A
def test_frozen_field_equality():
    """Scalar reconstruction == canonical exp01c pipeline, bit-for-bit.

    The canonical pipeline (prepare_intervals + add_flow_state) defines
    flow-state values exactly for the eligible rows; every eligible
    event must match, and the canonical row count must equal the
    eligible count (re-verifying the frozen anchor through the
    canonical path).
    """
    ok = True
    for hour in HOURS:
        d07, d09 = _tapes(hour)
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", RuntimeWarning)
            canonical = build_analysis_frame(d09.copy())
        canon_by_key = {}
        for row in canonical.itertuples(index=False):
            canon_by_key[(row.episode_id, row.t1_event_time_ms)] = row
        n = 0
        bad = None
        for st in iter_states(d07, d09, hour):
            if not st.has_interval:
                continue
            sig = signal_from_state(st)
            if not sig.signal_eligible:
                continue
            n += 1
            c = canon_by_key[(st.episode_id, st.event_time_ms)]
            if sig.flow_sign != c.flow_sign:
                bad = "flow_sign"; break
            if sig.flow_side != c.flow_side:
                bad = "flow_side"; break
            if sig.flow_magnitude != c.flow_magnitude:
                bad = "flow_magnitude"; break
            if not _same_float(sig.flow_purity, c.flow_purity):
                bad = "flow_purity"; break
            if not _same_float(sig.opposing_near_net_qty, c.opposing_near_net_qty):
                bad = "opposing_near_net_qty"; break
            if not _same_float(sig.opposing_near_add_qty, c.opposing_near_add_qty):
                bad = "opposing_near_add_qty"; break
            if not _same_float(sig.opposing_near_remove_qty, c.opposing_near_remove_qty):
                bad = "opposing_near_remove_qty"; break
            if not _same_float(sig.opposing_depth_t0, c.opposing_depth_t0):
                bad = "opposing_depth_t0"; break
            if sig.liquidity_response != c.liquidity_response:
                bad = "liquidity_response"; break
        if bad is not None:
            ok = check(f"{hour}: frozen field equality", False,
                       f"eligible event {n}: {bad} differs from canonical") and ok
        elif n != len(canonical):
            ok = check(f"{hour}: frozen field equality", False,
                       f"eligible {n} != canonical rows {len(canonical)}") and ok
        else:
            ok = check(f"{hour}: frozen field equality", True,
                       f"{n} eligible events bit-for-bit") and ok
    return ok


# ----------------------------------------------------------------- gate B
def test_eligibility_counts():
    """Frozen anchor eligibility counts, per-hour and aggregate."""
    ok = True
    total = 0
    for hour in HOURS:
        d07, d09 = _tapes(hour)
        n_elig = sum(
            1 for sig in iter_signals(d07, d09, hour) if sig.signal_eligible
        )
        total += n_elig
        exp = ELIGIBLE_EXPECTED[hour]
        ok = check(f"{hour}: eligible == {exp}", n_elig == exp,
                   f"got={n_elig}") and ok
    ok = check(f"combined eligible == {ELIGIBLE_TOTAL}",
               total == ELIGIBLE_TOTAL, f"got={total}") and ok
    return ok


# ----------------------------------------------------------------- gate C
def test_side_semantics():
    """BUY always references ASK 0-5 tick liquidity; SELL always BID."""
    ok = True
    for hour in HOURS:
        d07, d09 = _tapes(hour)
        n = 0
        bad = None
        for st in iter_states(d07, d09, hour):
            if not st.has_interval:
                continue
            n += 1
            sig = signal_from_state(st)
            iv = st.interval_fields
            if sig.flow_side == "BUY":
                if sig.opposing_near_net_qty != iv["ask_net_0_5_qty"]:
                    bad = "BUY net not ASK 0-5"; break
                if sig.opposing_near_add_qty != iv["ask_add_0_5_qty"]:
                    bad = "BUY add not ASK 0-5"; break
                if sig.opposing_near_remove_qty != iv["ask_remove_0_5_qty"]:
                    bad = "BUY remove not ASK 0-5"; break
                if sig.opposing_depth_t0 != iv["ask_depth5_t0"]:
                    bad = "BUY depth not ASK t0"; break
            else:
                if sig.opposing_near_net_qty != iv["bid_net_0_5_qty"]:
                    bad = "SELL net not BID 0-5"; break
                if sig.opposing_near_add_qty != iv["bid_add_0_5_qty"]:
                    bad = "SELL add not BID 0-5"; break
                if sig.opposing_near_remove_qty != iv["bid_remove_0_5_qty"]:
                    bad = "SELL remove not BID 0-5"; break
                if sig.opposing_depth_t0 != iv["bid_depth5_t0"]:
                    bad = "SELL depth not BID t0"; break
        if bad is not None:
            ok = check(f"{hour}: side semantics", False, f"state {n}: {bad}") and ok
        else:
            ok = check(f"{hour}: side semantics", True, f"{n} intervals") and ok
    return ok


# ----------------------------------------------------------------- gate D
def test_response_semantics():
    """positive -> REPLENISHMENT, negative -> DEPLETION, zero -> NEUTRAL."""
    ok = True
    for hour in HOURS:
        d07, d09 = _tapes(hour)
        n = 0
        bad = None
        for sig in iter_signals(d07, d09, hour):
            if not sig.has_interval:
                continue
            n += 1
            net = sig.opposing_near_net_qty
            if net > 0 and sig.liquidity_response != RESPONSE_REPLENISHMENT:
                bad = "positive net not REPLENISHMENT"; break
            if net < 0 and sig.liquidity_response != RESPONSE_DEPLETION:
                bad = "negative net not DEPLETION"; break
            if net == 0 and sig.liquidity_response != RESPONSE_NEUTRAL:
                bad = "zero net not NEUTRAL"; break
        if bad is not None:
            ok = check(f"{hour}: response semantics", False, f"state {n}: {bad}") and ok
        else:
            ok = check(f"{hour}: response semantics", True, f"{n} intervals") and ok
    # frozen response-class counts among eligible events
    rep_counts = {"DEPLETION": 0, "REPLENISHMENT": 0, "NEUTRAL": 0}
    for hour in HOURS:
        d07, d09 = _tapes(hour)
        counts = {"DEPLETION": 0, "REPLENISHMENT": 0, "NEUTRAL": 0}
        for sig in iter_signals(d07, d09, hour):
            if sig.signal_eligible:
                counts[sig.liquidity_response] += 1
        if hour == DISCOVERY_HOUR:
            exp = RESPONSE_EXPECTED[hour]
            for cls in ("DEPLETION", "REPLENISHMENT", "NEUTRAL"):
                ok = check(f"{hour}: eligible {cls} == {exp[cls]}",
                           counts[cls] == exp[cls], f"got={counts[cls]}") and ok
        else:
            for cls in ("DEPLETION", "REPLENISHMENT", "NEUTRAL"):
                rep_counts[cls] += counts[cls]
    exp = RESPONSE_EXPECTED["replication"]
    for cls in ("DEPLETION", "REPLENISHMENT", "NEUTRAL"):
        ok = check(f"replication: eligible {cls} == {exp[cls]}",
                   rep_counts[cls] == exp[cls], f"got={rep_counts[cls]}") and ok
    return ok


# ----------------------------------------------------------------- gate E
def test_no_lookahead():
    """Signal formation uses only current event / attached interval info."""
    ok = True
    # structural: the complete input field set contains no future-derived column
    if any("future" in f for f in SIGNAL_INPUT_FIELDS):
        ok = check("signal input fields: no future-derived columns", False,
                   f"found {sorted(f for f in SIGNAL_INPUT_FIELDS if 'future' in f)}") and ok
    else:
        ok = check("signal input fields: no future-derived columns", True,
                   f"{len(SIGNAL_INPUT_FIELDS)} fields") and ok
    for hour in HOURS:
        d07, d09 = _tapes(hour)
        n = 0
        bad = None
        for st in iter_states(d07, d09, hour):
            if not st.has_interval:
                continue
            n += 1
            if any("future" in c for c in st.interval_fields):
                bad = "interval row contains a future-derived column"
                break
            if any("future" in c for c in st.event_fields):
                bad = "event row contains a future-derived column"
                break
        if bad is not None:
            ok = check(f"{hour}: no lookahead", False, f"state {n}: {bad}") and ok
        else:
            ok = check(f"{hour}: no lookahead", True, f"{n} intervals") and ok
    return ok


# ----------------------------------------------------------------- gate F
def test_episode_first_behavior():
    """has_interval=False events must not fabricate a signal state."""
    ok = True
    total_first = 0
    for hour in HOURS:
        d07, d09 = _tapes(hour)
        n_first = 0
        bad = None
        for st in iter_states(d07, d09, hour):
            if st.has_interval:
                continue
            n_first += 1
            sig = signal_from_state(st)
            if sig.has_interval:
                bad = "signal claims an interval"; break
            if sig.signal_eligible:
                bad = "signal claims eligibility"; break
            if sig.flow_sign is not None or sig.flow_side is not None:
                bad = "signal fabricated flow state"; break
            if sig.flow_magnitude is not None or sig.flow_purity is not None:
                bad = "signal fabricated magnitude/purity"; break
            if sig.opposing_near_net_qty is not None:
                bad = "signal fabricated opposing liquidity"; break
            if sig.liquidity_response is not None or sig.signal_direction is not None:
                bad = "signal fabricated response/direction"; break
        total_first += n_first
        exp = d07["episode_id"].nunique()
        if bad is not None:
            ok = check(f"{hour}: episode-first behavior", False, bad) and ok
        elif n_first != exp:
            ok = check(f"{hour}: episode-first behavior", False,
                       f"interval-less {n_first} != episodes {exp}") and ok
        else:
            ok = check(f"{hour}: episode-first behavior", True,
                       f"{n_first} events, no fabricated signal") and ok
    ok = check("total episode-first events == 1,157", total_first == 1157,
               f"got={total_first}") and ok
    return ok


# ----------------------------------------------------------------- gate G
def test_determinism():
    """Same state input => same signal state."""
    ok = True
    for hour in HOURS:
        d07, d09 = _tapes(hour)
        it_a = iter_signals(d07, d09, hour)
        it_b = iter_signals(d07, d09, hour)
        n = 0
        bad = None
        for sa, sb in zip(it_a, it_b):
            n += 1
            if sa != sb:
                # SignalState equality is NaN-sensitive; compare NaN-aware.
                if not (
                    sa.source_hour == sb.source_hour
                    and sa.episode_id == sb.episode_id
                    and sa.event_index == sb.event_index
                    and sa.event_time_ms == sb.event_time_ms
                    and sa.has_interval == sb.has_interval
                    and sa.signal_eligible == sb.signal_eligible
                    and sa.flow_sign == sb.flow_sign
                    and sa.flow_side == sb.flow_side
                    and _same_float(sa.flow_magnitude, sb.flow_magnitude)
                    and _same_float(sa.flow_purity, sb.flow_purity)
                    and _same_float(sa.opposing_near_net_qty, sb.opposing_near_net_qty)
                    and _same_float(sa.opposing_near_add_qty, sb.opposing_near_add_qty)
                    and _same_float(sa.opposing_near_remove_qty, sb.opposing_near_remove_qty)
                    and _same_float(sa.opposing_depth_t0, sb.opposing_depth_t0)
                    and sa.liquidity_response == sb.liquidity_response
                    and sa.signal_direction == sb.signal_direction
                ):
                    bad = f"signal {n} differs between passes"
                    break
        if bad is None and (next(it_a, None) is not None or next(it_b, None) is not None):
            bad = "sequence lengths differ between passes"
        if bad is not None:
            ok = check(f"{hour}: determinism", False, bad) and ok
        else:
            ok = check(f"{hour}: determinism", True, f"{n} identical signals") and ok
    return ok


# ----------------------------------------------------------------- gate H
def test_input_immutability():
    """PE-2 must not mutate PE-1/D09B inputs."""
    ok = True
    for hour in HOURS:
        d07, d09 = _tapes(hour)
        d07_copy = d07.copy(deep=True)
        d09_copy = d09.copy(deep=True)
        n = 0
        bad = None
        for st in iter_states(d07, d09, hour):
            if not st.has_interval:
                continue
            n += 1
            snap = dict(st.interval_fields)
            sig = signal_from_state(st)
            if not _same_dict(st.interval_fields, snap):
                bad = f"interval dict mutated at state {n}"
                break
        try:
            pd.testing.assert_frame_equal(d07, d07_copy)
            pd.testing.assert_frame_equal(d09, d09_copy)
            frames_ok = True
        except AssertionError as exc:
            frames_ok = False
            frame_detail = str(exc).splitlines()[0]
        if bad is not None:
            ok = check(f"{hour}: input immutability", False, bad) and ok
        elif not frames_ok:
            ok = check(f"{hour}: input immutability", False, frame_detail) and ok
        else:
            ok = check(f"{hour}: input immutability", True,
                       f"{n} intervals, frames + dicts unchanged") and ok
    return ok


def main():
    ok = True
    ok = test_frozen_field_equality() and ok
    ok = test_eligibility_counts() and ok
    ok = test_side_semantics() and ok
    ok = test_response_semantics() and ok
    ok = test_no_lookahead() and ok
    ok = test_episode_first_behavior() and ok
    ok = test_determinism() and ok
    ok = test_input_immutability() and ok
    print("\n" + ("ALL PE-2 SIGNAL GATES PASSED" if ok else "PE-2 SIGNAL GATES FAILED"))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())