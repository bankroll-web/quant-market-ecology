"""
PE-2: frozen EXP-01 signal-state reconstruction (MODE A observation).

At each interval-bearing event, reconstruct the frozen EXP-01 signal
state from the attached D09B interval fields only, using the exact
canonical formulas (single source of truth: src/analysis/exp01.py,
add_flow_state):

  - aggressor: signed_flow_qty > 0 -> BUY, < 0 -> SELL
  - opposing side: BUY -> ASK, SELL -> BID (near-touch 0-5 ticks,
    PRE-event touch-derived D09B quantities; spatial definitions frozen)
  - response: opposing near-touch net > 0 -> REPLENISHMENT,
    < 0 -> DEPLETION, == 0 -> NEUTRAL (no tolerance bands)
  - eligibility (frozen anchor): trades_exactly_at_t1 == 0 AND
    total_flow_qty > 0 AND signed_flow_qty != 0 (no other filter)
  - MODE A directional hypothesis (observation only, creates no
    simulated order): DEPLETION + BUY -> LONG, DEPLETION + SELL -> SHORT,
    REPLENISHMENT -> COMPARATOR, NEUTRAL -> NEUTRAL; defined only for
    signal_eligible events (None otherwise)

No execution, latency, costs, exits, filters, or optimization.
No future H1/H3/H5/H10 fields, Y_h values, or future returns enter
signal formation (SIGNAL_INPUT_FIELDS is the complete input set).

The scalar implementation is cross-checked bit-for-bit against the
canonical vectorized add_flow_state by tests/test_paper_engine_signal.py
(gate A); the scientific definition is never forked silently.
"""
from dataclasses import dataclass
from typing import Iterator, Mapping, Optional

import pandas as pd

from .state import CausalState, iter_states

# Complete set of interval fields consumed for signal formation.
# No future-derived column may ever be added here (gate E).
SIGNAL_INPUT_FIELDS = frozenset(
    {
        "signed_flow_qty",
        "total_flow_qty",
        "ask_net_0_5_qty",
        "bid_net_0_5_qty",
        "ask_add_0_5_qty",
        "bid_add_0_5_qty",
        "ask_remove_0_5_qty",
        "bid_remove_0_5_qty",
        "ask_depth5_t0",
        "bid_depth5_t0",
        "trades_exactly_at_t1",
    }
)

RESPONSE_REPLENISHMENT = "REPLENISHMENT"
RESPONSE_DEPLETION = "DEPLETION"
RESPONSE_NEUTRAL = "NEUTRAL"

DIRECTION_LONG = "LONG"
DIRECTION_SHORT = "SHORT"
DIRECTION_COMPARATOR = "COMPARATOR"
DIRECTION_NEUTRAL = "NEUTRAL"


@dataclass(frozen=True)
class SignalState:
    """Frozen EXP-01 signal state at one event (MODE A observation)."""

    source_hour: str
    episode_id: int
    event_index: int
    event_time_ms: int
    has_interval: bool
    signal_eligible: bool
    flow_sign: Optional[int]
    flow_side: Optional[str]
    flow_magnitude: Optional[float]
    flow_purity: Optional[float]
    opposing_near_net_qty: Optional[float]
    opposing_near_add_qty: Optional[float]
    opposing_near_remove_qty: Optional[float]
    opposing_depth_t0: Optional[float]
    liquidity_response: Optional[str]
    signal_direction: Optional[str]


def _signal_from_interval(iv: Mapping[str, object]):
    """Scalar reconstruction of the frozen EXP-01 signal fields.

    Mirrors add_flow_state exactly for the shared fields: flow_sign,
    flow_side, flow_magnitude, flow_purity, opposing_near_net_qty,
    opposing_near_add_qty, opposing_near_remove_qty, opposing_depth_t0,
    liquidity_response. Eligibility and the MODE A direction label are
    PE-2 additions defined on the frozen fields.
    """
    signed_flow_qty = iv["signed_flow_qty"]
    total_flow_qty = iv["total_flow_qty"]

    flow_sign = 1 if signed_flow_qty > 0 else (-1 if signed_flow_qty < 0 else 0)
    flow_side = "BUY" if flow_sign > 0 else "SELL"
    flow_magnitude = abs(signed_flow_qty)
    if total_flow_qty != 0:
        flow_purity = flow_magnitude / total_flow_qty
    else:
        flow_purity = float("nan")  # canonical: 0.0 / 0.0 -> NaN

    if flow_sign > 0:
        opposing_near_net_qty = iv["ask_net_0_5_qty"]
        opposing_near_add_qty = iv["ask_add_0_5_qty"]
        opposing_near_remove_qty = iv["ask_remove_0_5_qty"]
        opposing_depth_t0 = iv["ask_depth5_t0"]
    else:
        opposing_near_net_qty = iv["bid_net_0_5_qty"]
        opposing_near_add_qty = iv["bid_add_0_5_qty"]
        opposing_near_remove_qty = iv["bid_remove_0_5_qty"]
        opposing_depth_t0 = iv["bid_depth5_t0"]

    if opposing_near_net_qty > 0:
        liquidity_response = RESPONSE_REPLENISHMENT
    elif opposing_near_net_qty < 0:
        liquidity_response = RESPONSE_DEPLETION
    else:
        liquidity_response = RESPONSE_NEUTRAL

    signal_eligible = (
        iv["trades_exactly_at_t1"] == 0
        and total_flow_qty > 0
        and signed_flow_qty != 0
    )

    if not signal_eligible:
        signal_direction = None
    elif liquidity_response == RESPONSE_DEPLETION:
        signal_direction = (
            DIRECTION_LONG if flow_side == "BUY" else DIRECTION_SHORT
        )
    elif liquidity_response == RESPONSE_REPLENISHMENT:
        signal_direction = DIRECTION_COMPARATOR
    else:
        signal_direction = DIRECTION_NEUTRAL

    return (
        signal_eligible,
        flow_sign,
        flow_side,
        flow_magnitude,
        flow_purity,
        opposing_near_net_qty,
        opposing_near_add_qty,
        opposing_near_remove_qty,
        opposing_depth_t0,
        liquidity_response,
        signal_direction,
    )


def signal_from_state(st: CausalState) -> SignalState:
    """Reconstruct the frozen EXP-01 signal state at one event.

    Events without an attached interval (has_interval=False) yield a
    SignalState with has_interval=False and all signal fields None: no
    signal state is fabricated from a nonexistent interval (gate F).
    """
    if not st.has_interval:
        return SignalState(
            source_hour=st.source_hour,
            episode_id=st.episode_id,
            event_index=st.event_index,
            event_time_ms=st.event_time_ms,
            has_interval=False,
            signal_eligible=False,
            flow_sign=None,
            flow_side=None,
            flow_magnitude=None,
            flow_purity=None,
            opposing_near_net_qty=None,
            opposing_near_add_qty=None,
            opposing_near_remove_qty=None,
            opposing_depth_t0=None,
            liquidity_response=None,
            signal_direction=None,
        )
    (
        signal_eligible,
        flow_sign,
        flow_side,
        flow_magnitude,
        flow_purity,
        opposing_near_net_qty,
        opposing_near_add_qty,
        opposing_near_remove_qty,
        opposing_depth_t0,
        liquidity_response,
        signal_direction,
    ) = _signal_from_interval(st.interval_fields)
    return SignalState(
        source_hour=st.source_hour,
        episode_id=st.episode_id,
        event_index=st.event_index,
        event_time_ms=st.event_time_ms,
        has_interval=True,
        signal_eligible=signal_eligible,
        flow_sign=flow_sign,
        flow_side=flow_side,
        flow_magnitude=flow_magnitude,
        flow_purity=flow_purity,
        opposing_near_net_qty=opposing_near_net_qty,
        opposing_near_add_qty=opposing_near_add_qty,
        opposing_near_remove_qty=opposing_near_remove_qty,
        opposing_depth_t0=opposing_depth_t0,
        liquidity_response=liquidity_response,
        signal_direction=signal_direction,
    )


def iter_signals(
    d07_df: pd.DataFrame,
    d09b_df: pd.DataFrame,
    source_hour: str,
) -> Iterator[SignalState]:
    """Yield one SignalState per D07 event, in tape order."""
    for st in iter_states(d07_df, d09b_df, source_hour):
        yield signal_from_state(st)