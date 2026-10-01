"""Assumed two-type exponential Hawkes trade arrivals via Ogata thinning."""
import math
import random


def hawkes(seed, seconds, base_rate=1.2, self_jump=0.5, cross_jump=0.1, decay=1.5):
    if (seconds <= 0 or base_rate <= 0 or min(self_jump, cross_jump) < 0 or
            decay <= 0 or (self_jump + cross_jump) / decay >= 1):
        raise ValueError('Positive duration/base/decay and stationary nonnegative kernel required')
    rng = random.Random(seed)
    excitation = [0., 0.]
    now, events = 0., []
    while True:
        bound = 2 * base_rate + sum(excitation)
        wait = rng.expovariate(bound)
        now += wait
        if now >= seconds:
            break
        excitation = [v * math.exp(-decay * wait) for v in excitation]
        intensity = [base_rate + v for v in excitation]
        if rng.random() * bound >= sum(intensity):
            continue
        direction = 0 if rng.random() * sum(intensity) < intensity[0] else 1
        events.append((now, 'buy' if direction == 0 else 'sell', rng.randint(1, 5)))
        excitation[direction] += self_jump
        excitation[1 - direction] += cross_jump
    return events
