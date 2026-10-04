"""Sample uniqueness weights for overlapping triple-barrier labels.

Neighbouring decisions whose outcome windows overlap share the same future
price path, so they are not independent samples. Average uniqueness measures
how much of its window an event has to itself:

    uniqueness_i = mean over t in [start_i, end_i) of 1 / concurrency(t)

1.0 means no overlap with any other event; 0.5 means on average one other
event is sharing the window. Use it as a training sample weight, or to
decide how sparsely to sample decisions.

Intervals are half-open [start, end) in integer nanoseconds. For label
overlap use start = decision time and end = label_available_ns (the same
end the purged splitter uses), so weighting and purging agree.
"""
from __future__ import annotations

import numpy as np


def average_uniqueness(starts, ends) -> np.ndarray:
    """O(n log n) average uniqueness per event via a sweep over breakpoints."""
    s = np.asarray(starts, dtype=np.int64)
    e = np.asarray(ends, dtype=np.int64)
    if s.shape != e.shape or s.ndim != 1:
        raise ValueError("starts and ends must be 1-D arrays of equal length")
    if s.size == 0:
        return np.empty(0)
    if np.any(e < s):
        raise ValueError("an interval ends before it starts")
    e = np.maximum(e, s + 1)  # zero-length event -> 1 ns so it has a window

    pts = np.unique(np.concatenate([s, e]))
    delta = np.zeros(pts.size, dtype=np.int64)
    np.add.at(delta, np.searchsorted(pts, s), 1)
    np.add.at(delta, np.searchsorted(pts, e), -1)
    conc = np.cumsum(delta)[:-1]                 # concurrency on [pts[i], pts[i+1])
    seg_len = np.diff(pts).astype(np.float64)
    inv = np.divide(1.0, conc, out=np.zeros_like(seg_len), where=conc > 0)
    cum = np.concatenate([[0.0], np.cumsum(seg_len * inv)])

    si = np.searchsorted(pts, s)
    ei = np.searchsorted(pts, e)
    return (cum[ei] - cum[si]) / (e - s).astype(np.float64)


def uniqueness_weights(starts, ends, normalize: bool = True) -> np.ndarray:
    """Sample weights from uniqueness. normalize=True rescales to sum to n,
    so the effective loss scale is unchanged versus unweighted training."""
    u = average_uniqueness(starts, ends)
    if normalize and u.sum() > 0:
        u = u * (u.size / u.sum())
    return u


def effective_sample_size(starts, ends) -> float:
    """Sum of uniqueness: overlap-equivalent label mass; not statistical independent sample count.
    Compare to len(starts); a large gap means you are over-counting."""
    return float(average_uniqueness(starts, ends).sum())


def sparse_sample(starts, ends) -> np.ndarray:
    """Greedy indices of a non-overlapping subset, chosen in time order.
    Returns indices into the ORIGINAL arrays. Non-overlapping windows, which can remain statistically dependent, at the
    cost of throwing data away; useful as a conservative cross-check."""
    s = np.asarray(starts, dtype=np.int64)
    e = np.asarray(ends, dtype=np.int64)
    order = np.argsort(s, kind="stable")
    keep, last_end = [], np.iinfo(np.int64).min
    for i in order:
        if s[i] >= last_end:
            keep.append(int(i))
            last_end = e[i]
    return np.asarray(keep, dtype=np.int64)
