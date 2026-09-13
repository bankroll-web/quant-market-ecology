"""
PE-1 test gate E: determinism.

Same input/order/config must produce the same PE-1 state sequence.
iter_states is a pure generator (no RNG, no mutation), so two full
passes over the same frames must yield identical states, including
NaN-valued fields (compared NaN-aware: NaN == NaN for this purpose).

Runs on all six validated hours, one hour at a time, comparing the two
passes lazily (no full materialization, per-hour memory discipline,
ledger O10). Tapes are read with the DEFAULT parser (ledger O11).

Run:  python tests/test_paper_engine_determinism.py
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


def _same_value(a, b):
    if isinstance(a, float) and isinstance(b, float):
        if pd.isna(a) and pd.isna(b):
            return True
    return a == b


def _same_dict(da, db):
    if da is None or db is None:
        return da is db
    if set(da) != set(db):
        return False
    return all(_same_value(da[k], db[k]) for k in da)


def _same_state(sa, sb):
    return (
        sa.source_hour == sb.source_hour
        and sa.episode_id == sb.episode_id
        and sa.event_index == sb.event_index
        and sa.event_time_ms == sb.event_time_ms
        and sa.is_episode_end == sb.is_episode_end
        and sa.has_interval == sb.has_interval
        and _same_dict(sa.event_fields, sb.event_fields)
        and _same_dict(sa.interval_fields, sb.interval_fields)
    )


def test_determinism():
    ok = True
    for hour in HOURS:
        d07, d09 = _tapes(hour)
        it_a = iter_states(d07, d09, hour)
        it_b = iter_states(d07, d09, hour)
        n = 0
        bad = None
        for sa, sb in zip(it_a, it_b):
            n += 1
            if not _same_state(sa, sb):
                bad = f"state {n} differs between passes"
                break
        if bad is None and (next(it_a, None) is not None or next(it_b, None) is not None):
            bad = "sequence lengths differ between passes"
        if bad is not None:
            ok = check(f"{hour}: determinism", False, bad) and ok
        else:
            ok = check(f"{hour}: determinism", True, f"{n} identical states") and ok
    return ok


def main():
    ok = test_determinism()
    print("\n" + ("ALL PE-1 DETERMINISM GATES PASSED" if ok else "PE-1 DETERMINISM GATES FAILED"))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())