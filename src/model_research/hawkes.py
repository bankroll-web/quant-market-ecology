"""Causal multivariate exponential Hawkes intensity filter.

lambda_i(t-) = mu_i + sum_j sum_{s<t,type(s)=j} alpha_ij exp(-beta(t-s)).
Seconds are used throughout; alpha[i][j] excites target i after source j.
This is a research adaptation, not the Hawkes LOB/PPO paper's full model.
No parameter fitting, event generation, execution, or trading is performed.
"""

from math import exp, isfinite


class ExponentialHawkes:
    """Stream strictly ordered observed events, returning pre-event intensities.

The maximum row sum of alpha/beta must be below one, a sufficient
(conservative) stationarity condition. Stable matrices outside this bound
are deliberately rejected. Each verified episode must call reset(); the
initial history is empty and early intensities have a warm-up transient.
"""

    def __init__(self, baseline, excitation, decay):
        self.baseline = tuple(float(x) for x in baseline)
        self.excitation = tuple(tuple(float(x) for x in row) for row in excitation)
        self.decay = float(decay)
        n = len(self.baseline)
        if not n or len(self.excitation) != n or any(len(row) != n for row in self.excitation):
            raise ValueError("excitation must be square and match baseline")
        if not isfinite(self.decay) or self.decay <= 0:
            raise ValueError("decay must be finite and positive")
        if any(not isfinite(x) or x < 0 for x in self.baseline):
            raise ValueError("baseline must be finite and nonnegative")
        if any(not isfinite(x) or x < 0 for row in self.excitation for x in row):
            raise ValueError("excitation must be finite and nonnegative")
        if max(sum(row) / self.decay for row in self.excitation) >= 1:
            raise ValueError("conservative stationarity bound requires max row sum(alpha/beta) < 1")
        self.reset()

    def reset(self):
        """Discard history at a gap, episode boundary, or new independent stream."""
        self._last_time = None
        self._excess = [0.0] * len(self.baseline)

    def intensity_at(self, time_seconds):
        """Read intensity without modifying history; cannot query the past."""
        t = float(time_seconds)
        if not isfinite(t):
            raise ValueError("time must be finite")
        if self._last_time is not None and t < self._last_time:
            raise ValueError("cannot query before last observed event")
        factor = 1.0 if self._last_time is None else exp(-self.decay * (t - self._last_time))
        return tuple(mu + x * factor for mu, x in zip(self.baseline, self._excess))

    def observe(self, time_seconds, event_type):
        """Return lambda(t-) then incorporate this event for future queries.

Tied timestamps are rejected: L2/trade timestamp buckets do not establish
the within-bucket order required here. Do not invent a tie ordering.
"""
        if isinstance(event_type, bool) or not isinstance(event_type, int) or not 0 <= event_type < len(self.baseline):
            raise ValueError("event_type must be an integer index")
        t = float(time_seconds)
        before = self.intensity_at(t)
        if self._last_time is not None and t <= self._last_time:
            raise ValueError("event times must be strictly increasing")
        self._excess = [before[i] - self.baseline[i] + self.excitation[i][event_type]
                        for i in range(len(self.baseline))]
        self._last_time = t
        return before
