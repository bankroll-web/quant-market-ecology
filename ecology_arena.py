"""
ecology_arena.py - a market-making ECOLOGY that runs on a laptop (numpy only).

IDEA: market-maker agents live on capital. Equity < 50% of start -> the agent DIES.
Equity > 200% of start -> it REPRODUCES (child = mutated copy, funded from the parent).
Policies are TOKEN-driven: each step the public tape is turned into a state token
(recent net aggressor flow x recent volatility = 15 states) and each agent has a
table that maps token -> (extra spread, directional quote shift).

WORLD (toy, 1 tick = 1 bp; read the caveats):
  * latent fair value with two volatility regimes + rare jumps
  * makers only see a LAGGED public price (lag steps) -> they can be picked off
  * noise traders hit quotes at random; informed traders know the value K steps ahead
    and trade only when it beats the best quote (ADVERSE SELECTION is built in)
  * per-fill fee in ticks paid by the maker (--fee); informed traders pay no fee

HONESTY CHECKS BUILT IN:
  * training = evolution on world seed A; scoring = FRESH world seeds, no evolution
  * evolved champions compete against a wide fixed spread and a simple tight-quote + inventory-skew rule
    (note: with a 1-tick grid, any half-spread up to 1 tick quotes the same price)
  * the same experiment is run with tokens disabled, so you can see if tokens matter
  * capital injected by "immigrants" is reported (no hidden free money)
CAVEATS: flow tokens carry information here only because informed traders exist in
this toy. Whether real BTC tapes leak as much is exactly what must be tested on real data.

    python ecology_arena.py --train-steps 60000 --test-steps 30000 --test-seeds 4
"""
import argparse
import numpy as np

S_FLOW, S_VOL = 5, 3
S = S_FLOW * S_VOL
WIN = 20            # token lookback (steps)
LIMIT = 10          # inventory limit per agent
C0 = 50.0           # starting capital (ticks)
RUIN, BIRTH = 0.5, 2.0


class World:
    """Pre-generated latent fair value path (so informed traders can look ahead K steps)."""
    def __init__(self, n, seed, lag=3, K=5, p_inf=0.15, noise_rate=0.6, base=10_000.0):
        rng = np.random.default_rng(seed)
        reg = np.zeros(n, dtype=int)
        flips = rng.random(n) < 0.002
        for t in range(1, n):
            reg[t] = 1 - reg[t - 1] if flips[t] else reg[t - 1]
        sig = np.where(reg == 0, 0.15, 0.6)
        jumps = (rng.random(n) < 0.001) * rng.choice([-5.0, 5.0], n)
        self.v = base + np.cumsum(sig * rng.standard_normal(n) + jumps)
        self.n, self.lag, self.K = n, lag, K
        self.p_inf, self.noise_n = p_inf, rng.poisson(noise_rate, n)
        self.noise_side = rng.choice([-1, 1], (n, 6))
        self.u_inf = rng.random(n)
        self.rng = rng

    def ref(self, t):
        return np.round(self.v[max(t - self.lag, 0)])

    def future(self, t):
        return self.v[min(t + self.K, self.n - 1)]


class Pop:
    def __init__(self, cap, use_tokens, rng):
        self.cap, self.use_tokens, self.rng = cap, use_tokens, rng
        z = np.zeros
        self.h, self.skew = z(cap), z(cap)
        self.w, self.d = z((cap, S)), z((cap, S))
        self.cash, self.inv = z(cap), z(cap)
        self.alive = z(cap, dtype=bool)
        self.birth, self.death, self.gen = z(cap, dtype=int), z(cap, dtype=int) - 1, z(cap, dtype=int)
        self.births = self.deaths = self.injected = 0

    def spawn(self, i, h, skew, w, d, t, gen, capital=C0):
        self.h[i], self.skew[i] = h, skew
        self.w[i], self.d[i] = w, d
        self.cash[i], self.inv[i] = capital, 0.0
        self.alive[i], self.birth[i], self.death[i], self.gen[i] = True, t, -1, gen

    def random_agent(self, i, t):
        r = self.rng
        self.spawn(i, r.uniform(1, 3), r.uniform(0, 0.2), np.zeros(S), np.zeros(S), t, 0)

    def mutate_from(self, i, p, t):
        r = self.rng
        h = float(np.clip(self.h[p] + r.normal(0, 0.25), 0.5, 6))
        sk = float(np.clip(self.skew[p] + r.normal(0, 0.03), 0, 0.6))
        if self.use_tokens:
            w = np.clip(self.w[p] + r.normal(0, 0.2, S) * (r.random(S) < 0.3), -1, 3)
            d = np.clip(self.d[p] + r.normal(0, 0.2, S) * (r.random(S) < 0.3), -2, 2)
        else:
            w, d = np.zeros(S), np.zeros(S)
        self.spawn(i, h, sk, w, d, t, self.gen[p] + 1)

    def equity(self, ref):
        return self.cash + self.inv * ref


def token_state(flow_cs, dref_cs, t):
    a = max(t - WIN, 0)
    net = flow_cs[t] - flow_cs[a]
    f = 0 if net <= -3 else 1 if net < 0 else 2 if net == 0 else 3 if net < 3 else 4
    vm = (dref_cs[t] - dref_cs[a]) / WIN
    vb = 0 if vm < 0.15 else 1 if vm < 0.35 else 2
    return f * S_VOL + vb


def run(pop, world, steps, fee, evolve, min_pop=12, log_every=0, label=""):
    rng = world.rng
    flow_cs = np.zeros(steps + 1)
    dref_cs = np.zeros(steps + 1)
    prev_ref = world.ref(0)
    for t in range(steps):
        ref = world.ref(t)
        tok = token_state(flow_cs, dref_cs, t) if pop.use_tokens else 0
        half = pop.h + (pop.w[:, tok] if pop.use_tokens else 0.0)
        shift = (pop.d[:, tok] if pop.use_tokens else 0.0) - pop.skew * pop.inv
        bid = np.floor(ref - np.maximum(half, 0.3) + shift)
        ask = np.maximum(np.ceil(ref + np.maximum(half, 0.3) + shift), bid + 1)
        net = 0
        orders = [("n", s) for s in world.noise_side[t, :min(world.noise_n[t], 6)]]
        if world.u_inf[t] < world.p_inf:
            orders.append(("i", 0))
        for kind, s in orders:
            ok_a = pop.alive & (pop.inv > -LIMIT)
            ok_b = pop.alive & (pop.inv < LIMIT)
            a = np.where(ok_a, ask, np.inf)
            b = np.where(ok_b, bid, -np.inf)
            if kind == "i":                                   # informed: trade only if it beats the quote
                fv = world.future(t)
                if fv > a.min():
                    s = 1
                elif fv < b.max():
                    s = -1
                else:
                    continue
            if s == 1 and np.isfinite(a.min()):                 # aggressive buy lifts best ask
                m = a.min()
                i = rng.choice(np.flatnonzero(a == m))
                pop.cash[i] += m - fee
                pop.inv[i] -= 1
                net += 1
            elif s == -1 and np.isfinite(b.max()):              # aggressive sell hits best bid
                m = b.max()
                i = rng.choice(np.flatnonzero(b == m))
                pop.cash[i] -= m + fee
                pop.inv[i] += 1
                net -= 1
        flow_cs[t + 1] = flow_cs[t] + net
        dref_cs[t + 1] = dref_cs[t] + abs(ref - prev_ref)
        prev_ref = ref
        eq = pop.equity(ref)
        dead = pop.alive & (eq < RUIN * C0)
        if dead.any():                                         # liquidate at ref and freeze
            for i in np.flatnonzero(dead):
                pop.cash[i] += pop.inv[i] * ref
                pop.inv[i] = 0.0
                pop.alive[i], pop.death[i] = False, t
                pop.deaths += 1
        if evolve:
            free = np.flatnonzero(~pop.alive)
            for p in np.flatnonzero(pop.alive & (eq >= BIRTH * C0)):
                if len(free) == 0:
                    break
                i, free = free[0], free[1:]
                pop.mutate_from(i, p, t)
                pop.cash[p] -= C0                              # child funded by the parent
                pop.births += 1
            if pop.alive.sum() < min_pop and len(free):        # immigration: new capital, tracked
                pop.random_agent(free[0], t)
                pop.injected += C0
        if log_every and (t + 1) % log_every == 0:
            al = pop.alive
            print(f"  [{label}] t={t + 1:6d} alive={al.sum():3d} births={pop.births:4d} deaths={pop.deaths:4d} "
                  f"mean_h={pop.h[al].mean():.2f} max_gen={pop.gen[al].max()} injected={pop.injected:.0f}")
    return pop.equity(world.ref(steps - 1)) - C0


def train(use_tokens, steps, fee, seed, cap=80, n0=40):
    rng = np.random.default_rng(seed + 1000)
    pop = Pop(cap, use_tokens, rng)
    for i in range(n0):
        pop.random_agent(i, 0)
    world = World(steps, seed)
    pnl = run(pop, world, steps, fee, evolve=True, log_every=steps // 4, label="tokens" if use_tokens else "blind ")
    al = np.flatnonzero(pop.alive)
    champs = al[np.argsort(-pnl[al])][:10]
    return pop, champs, pnl


def arena_test(pop_src, champs, use_tokens, steps, fee, seed):
    """Fresh world; no evolution. 10 agents each: wide fixed spread, tight quotes + inventory skew
    (a simple rule that is already close to tuned), and evolved champions - all competing."""
    rng = np.random.default_rng(seed + 5000)
    pop = Pop(30, use_tokens, rng)
    for i in range(10):
        pop.spawn(i, 2.0, 0.0, np.zeros(S), np.zeros(S), 0, 0)
    for i in range(10, 20):
        pop.spawn(i, 1.0, 0.15, np.zeros(S), np.zeros(S), 0, 0)
    for j, i in enumerate(range(20, 30)):
        c = champs[j % len(champs)]
        pop.spawn(i, pop_src.h[c], pop_src.skew[c], pop_src.w[c].copy(), pop_src.d[c].copy(), 0, 0)
    pnl = run(pop, World(steps, seed), steps, fee, evolve=False)
    return [pnl[:10].mean(), pnl[10:20].mean(), pnl[20:].mean()], [pop.alive[:10].mean(), pop.alive[10:20].mean(),
                                                                  pop.alive[20:].mean()]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--train-steps", type=int, default=60_000)
    ap.add_argument("--test-steps", type=int, default=30_000)
    ap.add_argument("--test-seeds", type=int, default=4)
    ap.add_argument("--fee", type=float, default=0.0, help="per-fill fee in ticks (1 tick = 1 bp in this toy)")
    ap.add_argument("--seed", type=int, default=1)
    a = ap.parse_args()
    results = {}
    for use_tokens in (True, False):
        name = "token-driven" if use_tokens else "token-blind"
        print(f"\n=== training {name} ecology ({a.train_steps} steps, fee {a.fee}) ===")
        pop, champs, pnl = train(use_tokens, a.train_steps, a.fee, a.seed)
        print(f"  champions' TRAIN pnl (selected on it, so optimistic): {np.round(pnl[champs][:5], 0)} ...")
        rows, surv = [], []
        for k in range(a.test_seeds):
            r, s = arena_test(pop, champs, use_tokens, a.test_steps, a.fee, seed=100 + k)
            rows.append(r)
            surv.append(s)
        results[name] = (np.array(rows), np.array(surv))
    print(f"\n=== FRESH-WORLD TEST: mean pnl per agent in ticks over {a.test_steps} steps, {a.test_seeds} new seeds ===")
    print(f"{'ecology':14s} {'wide fixed':>13s} {'tight+skew':>11s} {'evolved':>10s}   evolved wins/seed  evolved survival")
    for name, (rows, surv) in results.items():
        m = rows.mean(0)
        wins = int((rows[:, 2] > np.maximum(rows[:, 0], rows[:, 1])).sum())
        print(f"{name:14s} {m[0]:13.1f} {m[1]:11.1f} {m[2]:10.1f}   {wins}/{len(rows)}               {surv[:, 2].mean():.0%}")
        print(f"{'':14s} per-seed evolved: {np.round(rows[:, 2], 1)}")
    print("\nRead it: evolved must beat BOTH baselines on most fresh seeds. Token-driven must beat token-blind to "
          "justify tokens. Profit in this toy is not evidence of profit on real BTC.")


if __name__ == "__main__":
    main()
