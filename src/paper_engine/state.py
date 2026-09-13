"""
PE-1: causal state reconstruction at each validated event.

A CausalState is the complete set of information observable at one event:
  - the D07 event row itself (book state, flow deltas, timestamps), and
  - the D09B joint interval row whose t1 event IS this event (flow
    quantities, touch-distance response buckets, interval book state).

The D09B interval (t0, t1] is only attached at its t1 event, so every
field is observable at the event time (no lookahead). Episode-first
events (no interval ending at them) are represented explicitly with
has_interval=False; they are never silently dropped.

Data integrity: every interval row must attach to exactly one event.
iter_states raises ValueError if any interval fails to attach or a
duplicate interval key appears.
"""
from dataclasses import dataclass
from typing import Iterator, Mapping, Optional

import pandas as pd

from .events import iter_events


@dataclass(frozen=True)
class CausalState:
    """All causally available information at one validated event."""

    source_hour: str
    episode_id: int
    event_index: int
    event_time_ms: int
    is_episode_end: bool
    has_interval: bool
    event_fields: Mapping[str, object]
    interval_fields: Optional[Mapping[str, object]]  # None iff not has_interval


def iter_states(
    d07_df: pd.DataFrame,
    d09b_df: pd.DataFrame,
    source_hour: str,
) -> Iterator[CausalState]:
    """Yield one CausalState per D07 event, in tape order.

    Attaches the D09B interval row whose t1_event_time_ms equals the
    event's event_time_ms (same episode). The `hour` column (replication
    tapes only) is identity metadata and is not carried as a state field.
    """
    # Interval lookup: (episode_id, t1_event_time_ms) -> row dict.
    lookup = {}
    for row in d09b_df.itertuples(index=False):
        d = row._asdict()
        d.pop("hour", None)
        key = (d["episode_id"], d["t1_event_time_ms"])
        if key in lookup:
            raise ValueError(f"duplicate interval key {key}")
        lookup[key] = d

    attached = 0
    for ev in iter_events(d07_df, source_hour):
        interval = lookup.get((ev.episode_id, ev.event_time_ms))
        if interval is not None:
            attached += 1
        yield CausalState(
            source_hour=ev.source_hour,
            episode_id=ev.episode_id,
            event_index=ev.event_index,
            event_time_ms=ev.event_time_ms,
            is_episode_end=ev.is_episode_end,
            has_interval=interval is not None,
            event_fields=ev.fields,
            interval_fields=interval,
        )
    if attached != len(d09b_df):
        raise ValueError(
            f"only {attached}/{len(d09b_df)} interval rows attached to events"
        )