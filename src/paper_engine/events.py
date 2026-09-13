"""
PE-1: sequential event iterator over validated D07 event tapes.

The D07 liquidity event tape is the validated, sorted sequence of valid L2
events (one row per event, grouped by episode, ordered by event_time_ms).
This module walks that tape in its exact stored order and attaches episode
identity (episode_id, event_index, is_episode_end) without reordering or
mutating the input.

Causal contract (PE-1 test gate A): every field of the yielded Event is
observable at the event itself. No field depends on any later event.

The tape is the validated causal sequence: if it is not grouped by
episode_id and sorted by event_time_ms, or contains duplicate
(episode_id, event_time_ms) keys, iter_events raises instead of silently
reordering or deduplicating.
"""
from dataclasses import dataclass
from typing import Iterator, Mapping

import pandas as pd


@dataclass(frozen=True)
class Event:
    """One validated D07 event with episode identity, in tape order."""

    source_hour: str
    episode_id: int
    event_index: int  # 0-based position within the episode
    event_time_ms: int
    is_episode_end: bool
    fields: Mapping[str, object]  # D07 row fields (all causal at this event)


def iter_events(d07_df: pd.DataFrame, source_hour: str) -> Iterator[Event]:
    """Yield D07 events in exact tape order with episode identity.

    Raises ValueError if the tape is not grouped by episode_id, not sorted
    by event_time_ms, or contains duplicate (episode_id, event_time_ms)
    keys. The `hour` column (replication tapes only) is identity metadata
    and is carried as source_hour, not as an event field.
    """
    if "episode_id" not in d07_df.columns or "event_time_ms" not in d07_df.columns:
        raise ValueError("D07 tape missing episode_id/event_time_ms columns")

    eps = d07_df["episode_id"].to_numpy()
    times = d07_df["event_time_ms"].to_numpy()
    n = len(d07_df)
    if n and (eps[1:] < eps[:-1]).any():
        raise ValueError("D07 tape not grouped by episode_id")
    if n and (times[1:] < times[:-1]).any():
        raise ValueError("D07 tape not sorted by event_time_ms")
    if d07_df.duplicated(["episode_id", "event_time_ms"]).any():
        raise ValueError("D07 tape contains duplicate (episode_id, event_time_ms)")

    event_index = d07_df.groupby("episode_id").cumcount().to_numpy()
    for i, row in enumerate(d07_df.itertuples(index=False)):
        d = row._asdict()
        d.pop("hour", None)
        episode_id = d["episode_id"]
        event_time_ms = d["event_time_ms"]
        is_episode_end = (i + 1 >= n) or (eps[i + 1] != eps[i])
        yield Event(
            source_hour=source_hour,
            episode_id=episode_id,
            event_index=event_index[i],
            event_time_ms=event_time_ms,
            is_episode_end=is_episode_end,
            fields=d,
        )