"""
PE-1 test gate: causal sequential iterator over validated tapes.

Gate A (no lookahead), B (event order), C (episode containment),
D (input immutability), F (missing/terminal events represented
explicitly). Gate E (determinism) lives in
test_paper_engine_determinism.py; gate G (upstream regression) is
run_tests.py itself.

Runs on all six validated hours (discovery + 5 replication), one hour at
a time (serial, per-hour memory discipline, ledger O10). Tapes are read
with the DEFAULT parser, matching the downstream-analysis convention
(ledger O11: downstream consumers read written files with the default
parser).

Run:  python tests/test_paper_engine_causality.py
"""
import os
import sys

import pandas as pd

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

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


# ----------------------------------------------------------------- gate A
def test_no_lookahead():
    """At event i, no state field may depend on event j where j > i."""
    ok = True
    for hour in HOURS:
        d07, d09 = _tapes(hour)
        n = 0
        bad = None
        for st in iter_states(d07, d09, hour):
            n += 1
            # 1. the event row is the current event (identity cross-check)
            if st.event_fields["event_time_ms"] != st.event_time_ms:
                bad = "event row is not the current event"
                break
            if st.event_fields["episode_id"] != st.episode_id:
                bad = "event row episode_id != state episode_id"
                break
            # 2. no future-prefixed columns in the event row
            if any("future" in c for c in st.event_fields):
                bad = "event row contains a future-derived column"
                break
            if st.has_interval:
                iv = st.interval_fields
                # 3. the attached interval ends at THIS event
                if iv["t1_event_time_ms"] != st.event_time_ms:
                    bad = "interval t1 is not the current event"
                    break
                if iv["event_time_ms"] != st.event_time_ms:
                    bad = "interval event_time_ms is not the current event"
                    break
                if iv["episode_id"] != st.episode_id:
                    bad = "interval episode_id != state episode_id"
                    break
                # 4. the interval start is strictly in the past
                if iv["t0_event_time_ms"] >= st.event_time_ms:
                    bad = "interval t0 is not strictly before the event"
                    break
                if iv["interval_ms"] != iv["t1_event_time_ms"] - iv["t0_event_time_ms"]:
                    bad = "interval_ms inconsistent with t0/t1"
                    break
                # 5. UTC strings: t1_utc is this event's UTC, t0_utc earlier
                if iv["t1_utc"] != st.event_fields["event_time_utc"]:
                    bad = "t1_utc != event_time_utc"
                    break
                if not iv["t0_utc"] < iv["t1_utc"]:
                    bad = "t0_utc not before t1_utc"
                    break
                # 6. no future-prefixed columns in the interval row
                if any("future" in c for c in iv):
                    bad = "interval row contains a future-derived column"
                    break
        if bad is not None:
            ok = check(f"{hour}: no lookahead", False, f"state {n}: {bad}") and ok
        else:
            ok = check(f"{hour}: no lookahead", True, f"{n} states") and ok
    return ok


# ----------------------------------------------------------------- gate B
def test_event_order():
    """Within each episode, timestamps are monotonic per the validated tape."""
    ok = True
    for hour in HOURS:
        d07, d09 = _tapes(hour)
        prev_ep = None
        prev_evt = None
        prev_recv = None
        prev_tx = None
        n = 0
        bad = None
        for st in iter_states(d07, d09, hour):
            n += 1
            evt = st.event_time_ms
            recv = st.event_fields["received_time_ns"]
            tx = st.event_fields["transaction_time_ms"]
            if st.episode_id != prev_ep:
                prev_ep = st.episode_id
                prev_evt = prev_recv = prev_tx = None
            else:
                if evt <= prev_evt:
                    bad = "event_time_ms not strictly increasing"
                    break
                if recv < prev_recv:
                    bad = "received_time_ns decreased"
                    break
                if tx < prev_tx:
                    bad = "transaction_time_ms decreased"
                    break
            if tx > evt:
                bad = "transaction_time_ms > event_time_ms"
                break
            prev_evt, prev_recv, prev_tx = evt, recv, tx
        if bad is not None:
            ok = check(f"{hour}: event order", False, f"state {n}: {bad}") and ok
        else:
            ok = check(f"{hour}: event order", True, f"{n} states") and ok
    return ok


# ----------------------------------------------------------------- gate C
def test_episode_containment():
    """The iterator never silently crosses episode boundaries."""
    ok = True
    for hour in HOURS:
        d07, d09 = _tapes(hour)
        seen = set()
        prev_ep = None
        expected_idx = 0
        n = 0
        n_ends = 0
        bad = None
        for st in iter_states(d07, d09, hour):
            n += 1
            if st.episode_id != prev_ep:
                if st.episode_id in seen:
                    bad = f"episode {st.episode_id} reappears after another episode"
                    break
                seen.add(st.episode_id)
                if st.event_index != 0:
                    bad = f"episode {st.episode_id} does not start at index 0"
                    break
                prev_ep = st.episode_id
                expected_idx = 1
            else:
                if st.event_index != expected_idx:
                    bad = f"episode {st.episode_id} index gap at state {n}"
                    break
                expected_idx += 1
            if st.is_episode_end:
                n_ends += 1
                expected_idx = 0
        if bad is not None:
            ok = check(f"{hour}: episode containment", False, bad) and ok
        elif n != len(d07):
            ok = check(f"{hour}: episode containment", False,
                       f"yielded {n} != tape {len(d07)}") and ok
        elif n_ends != d07["episode_id"].nunique():
            ok = check(f"{hour}: episode containment", False,
                       f"episode ends {n_ends} != episodes {d07['episode_id'].nunique()}") and ok
        else:
            ok = check(f"{hour}: episode containment", True,
                       f"{n} events, {n_ends} episodes") and ok
    return ok


# ----------------------------------------------------------------- gate D
def test_input_immutability():
    """PE-1 must not mutate D07/D09B input frames."""
    ok = True
    for hour in HOURS:
        d07, d09 = _tapes(hour)
        d07_copy = d07.copy(deep=True)
        d09_copy = d09.copy(deep=True)
        n = sum(1 for _ in iter_states(d07, d09, hour))
        try:
            pd.testing.assert_frame_equal(d07, d07_copy)
            pd.testing.assert_frame_equal(d09, d09_copy)
            ok = check(f"{hour}: input immutability", True, f"{n} states") and ok
        except AssertionError as exc:
            ok = check(f"{hour}: input immutability", False,
                       str(exc).splitlines()[0]) and ok
    return ok


# ----------------------------------------------------------------- gate F
def test_terminal_and_missing():
    """Episode endings and incomplete interval state are explicit, not dropped."""
    ok = True
    for hour in HOURS:
        d07, d09 = _tapes(hour)
        n = 0
        n_intervals = 0
        n_first = 0
        n_ends = 0
        bad = None
        for st in iter_states(d07, d09, hour):
            n += 1
            if st.has_interval:
                n_intervals += 1
                if st.event_index == 0:
                    bad = f"episode {st.episode_id} first event has an interval"
                    break
            else:
                n_first += 1
                if st.event_index != 0:
                    bad = f"state {n}: non-first event without interval"
                    break
            if st.is_episode_end:
                n_ends += 1
        if bad is not None:
            ok = check(f"{hour}: terminal/missing explicit", False, bad) and ok
        elif n != len(d07):
            ok = check(f"{hour}: terminal/missing explicit", False,
                       f"yielded {n} != tape {len(d07)}") and ok
        elif n_intervals != len(d09):
            ok = check(f"{hour}: terminal/missing explicit", False,
                       f"attached {n_intervals} != intervals {len(d09)}") and ok
        elif n_first != d07["episode_id"].nunique():
            ok = check(f"{hour}: terminal/missing explicit", False,
                       f"interval-less {n_first} != episodes {d07['episode_id'].nunique()}") and ok
        elif n_ends != d07["episode_id"].nunique():
            ok = check(f"{hour}: terminal/missing explicit", False,
                       f"episode ends {n_ends} != episodes {d07['episode_id'].nunique()}") and ok
        elif n_intervals != n - n_first:
            ok = check(f"{hour}: terminal/missing explicit", False,
                       f"accounting identity broken: intervals {n_intervals} != events {n} - episode-first {n_first}") and ok
        else:
            ok = check(f"{hour}: terminal/missing explicit", True,
                       f"{n} events, {n_intervals} intervals, {n_first} episode-first "
                       f"(identity: {n} - {n_first} == {n_intervals})") and ok
    return ok


def main():
    ok = True
    ok = test_no_lookahead() and ok
    ok = test_event_order() and ok
    ok = test_episode_containment() and ok
    ok = test_input_immutability() and ok
    ok = test_terminal_and_missing() and ok
    print("\n" + ("ALL PE-1 CAUSALITY GATES PASSED" if ok else "PE-1 CAUSALITY GATES FAILED"))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())