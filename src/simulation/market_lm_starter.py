"""
market_lm.py - tokenized order-flow model for BTC (starter skeleton)

PIPELINE
  raw events -> QuantileBinner (fit on TRAIN ONLY) -> 5 field tokens per event
  -> causal transformer (field embeddings summed into one vector per event)
  -> heads: next-event fields + return quantiles + volatility + signed flow

TARGETS (all measured from the mid price right AFTER event t)
  returns : log(mid[t+h] / mid[t]) for h in HORIZONS (events), z-scored on train
  vol     : log of mean |1-event log return| over the next VOL_WIN events
  flow    : signed traded size / total traded size over the next VOL_WIN events

LOSSES
  fields   : cross-entropy; LEVEL/SIZE/DT use neighbor-aware (Gaussian-smoothed) targets
  returns  : pinball (quantile) loss, non-crossing quantiles by construction
  vol/flow : MSE
EVAL
  walk-forward folds with a purge gap, pinball vs unconditional baseline,
  80% band coverage, optional split-conformal widening.

Replace make_synthetic() with real data (e.g. Tardis/Kaiko L2/L3 events) that
has the same columns. NOT tested end-to-end on real data; audit before trusting.
"""
import argparse
import math
import numpy as np
import torch
import torch.nn as nn
import torch.nn.functional as F

FIELDS = ["type", "side", "level", "size", "dt"]
N_TOK = dict(type=4, side=2, level=64, size=32, dt=32)   # type: 0 trade,1 add,2 cancel,3 modify
ORDINAL = {"level": 1.5, "size": 1.0, "dt": 1.0}         # field -> smoothing sigma (in bins)
HORIZONS = [10, 50, 200]
QUANTILES = [0.1, 0.25, 0.5, 0.75, 0.9]
VOL_WIN = 50
MAX_H = max(HORIZONS + [VOL_WIN])


# ----------------------------------------------------------------- data ----
def make_synthetic(n=200_000, seed=0):
    """Fake event stream with volatility clustering + a weak flow->return link."""
    rng = np.random.default_rng(seed)
    ls = np.zeros(n)
    for i in range(1, n):
        ls[i] = 0.995 * ls[i - 1] + 0.1 * rng.standard_normal()
    sig = 1e-4 * np.exp(ls)
    typ = rng.choice(4, n, p=[0.20, 0.45, 0.30, 0.05])
    side = rng.integers(0, 2, n)
    ret = sig * rng.standard_t(4, n) + 0.05 * sig * (2 * side - 1) * (typ == 0)
    return dict(
        type=typ, side=side,
        level_ticks=rng.laplace(0, 3 * sig / 1e-4) * rng.choice([-1, 1], n),
        size=np.exp(rng.normal(-2, 1, n)),
        dt=rng.exponential(1.0 / (sig / 1e-4)),
        mid=50_000 * np.exp(np.cumsum(ret)),
    )


class QuantileBinner:
    """Quantile bins fit on past data only (no look-ahead)."""
    def __init__(self, n_bins):
        self.n = n_bins
        self.edges = None

    def fit(self, x):
        self.edges = np.quantile(x, np.linspace(0, 1, self.n + 1)[1:-1])
        return self

    def transform(self, x):
        return np.searchsorted(self.edges, x).astype(np.int64)


def build_dataset(raw, train_end):
    """Tokens + targets. Binners and scalers use raw[:train_end] ONLY."""
    N = len(raw["mid"])
    if not MAX_H + 2 < train_end <= N: raise ValueError("Insufficient resolved training history")
    if any(len(raw[k]) != N for k in ("type","side","level_ticks","size","dt")): raise ValueError("Misaligned fields")
    if not all(np.isfinite(raw[k]).all() for k in raw) or np.any(raw["mid"] <= 0) or np.any(raw["size"] < 0) or np.any(raw["dt"] < 0): raise ValueError("Invalid raw values")
    cols = dict(type=raw["type"], side=raw["side"])
    for f, key in [("level", "level_ticks"), ("size", "size"), ("dt", "dt")]:
        values = np.log1p(raw[key]) if f in ("size","dt") else raw[key]
        b = QuantileBinner(N_TOK[f]).fit(values[:train_end])
        cols[f] = b.transform(values)
    tokens = np.stack([cols[f] for f in FIELDS], 1)

    lr = np.log(raw["mid"])
    R = np.full((N, len(HORIZONS)), np.nan)
    for j, h in enumerate(HORIZONS):
        R[:N - h, j] = lr[h:] - lr[:N - h]
    mu_r = np.array([np.mean(R[:train_end-h, j]) for j,h in enumerate(HORIZONS)])
    sd_r = np.array([max(np.std(R[:train_end-h, j]), 1e-8) for j,h in enumerate(HORIZONS)])
    R = (R - mu_r) / sd_r

    step = np.abs(np.diff(lr, prepend=lr[0]))
    cs = np.cumsum(step)
    vol = np.full(N, np.nan)
    vol[:N - VOL_WIN] = np.log((cs[VOL_WIN:] - cs[:N - VOL_WIN]) / VOL_WIN + 1e-12)
    vol_mu = np.mean(vol[:train_end-VOL_WIN])
    vol_sd = max(np.std(vol[:train_end-VOL_WIN]), 1e-8)
    vol = (vol - vol_mu) / vol_sd

    traded = raw["size"] * (raw["type"] == 0)
    signed = traded * (2 * raw["side"] - 1)
    cf, ca = np.cumsum(signed), np.cumsum(traded)
    flow = np.full(N, np.nan)
    flow[:N - VOL_WIN] = (cf[VOL_WIN:] - cf[:N - VOL_WIN]) / (ca[VOL_WIN:] - ca[:N - VOL_WIN] + 1e-9)

    return dict(scaler=dict(return_mean=mu_r.tolist(),return_std=sd_r.tolist(),vol_mean=float(vol_mu),vol_std=float(vol_sd)), tokens=torch.tensor(tokens), R=torch.tensor(R, dtype=torch.float32),
                vol=torch.tensor(vol, dtype=torch.float32), flow=torch.tensor(flow, dtype=torch.float32))


def get_batch(D, starts, L):
    idx = torch.stack([torch.arange(s, s + L + 1) for s in starts])     # L+1 events
    x = D["tokens"][idx]
    return dict(x=x[:, :-1], y=x[:, 1:], R=D["R"][idx[:, :-1]],
                vol=D["vol"][idx[:, :-1]], flow=D["flow"][idx[:, :-1]])


# ---------------------------------------------------------------- model ----
class MarketLM(nn.Module):
    def __init__(self, d=128, layers=4, heads=4, max_len=512):
        super().__init__()
        self.max_len = max_len
        self.emb = nn.ModuleDict({"field_"+f: nn.Embedding(N_TOK[f], d) for f in FIELDS})
        self.pos = nn.Embedding(max_len, d)
        layer = nn.TransformerEncoderLayer(d, heads, 4 * d, 0.1, batch_first=True, norm_first=True)
        self.enc = nn.TransformerEncoder(layer, layers, enable_nested_tensor=False)
        self.norm = nn.LayerNorm(d)
        self.heads = nn.ModuleDict({"field_"+f: nn.Linear(d, N_TOK[f]) for f in FIELDS})
        self.q = nn.Linear(d, len(HORIZONS) * len(QUANTILES))
        self.vol = nn.Linear(d, 1)
        self.flow = nn.Linear(d, 1)

    def forward(self, x):
        B, T, _ = x.shape
        h = sum(self.emb["field_"+f](x[..., i]) for i, f in enumerate(FIELDS))
        h = h + self.pos(torch.arange(T, device=x.device))
        mask = torch.triu(torch.ones(T, T, dtype=torch.bool, device=x.device), 1)
        h = self.norm(self.enc(h, mask=mask))
        raw = self.q(h).view(B, T, len(HORIZONS), len(QUANTILES))
        gaps = F.softplus(raw[..., 1:])                                  # non-crossing quantiles
        q = torch.cat([raw[..., :1], raw[..., :1] + torch.cumsum(gaps, -1)], -1)
        return dict(fields={f: self.heads["field_"+f](h) for f in FIELDS}, q=q,
                    vol=self.vol(h).squeeze(-1), flow=torch.tanh(self.flow(h)).squeeze(-1))


# --------------------------------------------------------------- losses ----
def soft_ce(logits, target, sigma):
    """Neighbor-aware CE: near-miss bins are penalized less than wild misses."""
    idx = torch.arange(logits.size(-1), device=logits.device)
    w = torch.exp(-0.5 * ((idx[None] - target[:, None]) / sigma) ** 2)
    w = w / w.sum(-1, keepdim=True)
    return -(w * F.log_softmax(logits, -1)).sum(-1)


def pinball(q, y):
    qs = torch.tensor(QUANTILES, device=q.device)
    d = y.unsqueeze(-1) - q
    return torch.maximum(qs * d, (qs - 1) * d)


def masked_mean(v, m):
    mask = torch.broadcast_to(m, v.shape)
    return (v * mask).sum() / mask.sum().clamp(min=1)


def compute_loss(model, b, w=dict(fields=1.0, q=1.0, vol=0.3, flow=0.3)):
    out = model(b["x"])
    parts = {}
    fl = 0.0
    for i, f in enumerate(FIELDS):
        lg, y = out["fields"][f].reshape(-1, N_TOK[f]), b["y"][..., i].reshape(-1)
        fl = fl + (soft_ce(lg, y, ORDINAL[f]) if f in ORDINAL else F.cross_entropy(lg, y, reduction="none")).mean()
    parts["fields"] = fl
    m = (~torch.isnan(b["R"])).float()
    parts["q"] = masked_mean(pinball(out["q"], torch.nan_to_num(b["R"])), m.unsqueeze(-1))
    mv = (~torch.isnan(b["vol"])).float()
    parts["vol"] = masked_mean((out["vol"] - torch.nan_to_num(b["vol"])) ** 2, mv)
    mf = (~torch.isnan(b["flow"])).float()
    parts["flow"] = masked_mean((out["flow"] - torch.nan_to_num(b["flow"])) ** 2, mf)
    total = sum(w[k] * parts[k] for k in parts)
    return total, {k: float(v) for k, v in parts.items()}


# ------------------------------------------------------- train / evaluate ----
def train(model, D, lo, hi, steps=300, bs=32, L=128, lr=3e-4, dev="cpu"):
    opt = torch.optim.AdamW(model.parameters(), lr=lr, weight_decay=0.01)
    last = hi - L - 1 - MAX_H                       # keep targets inside the train range
    model.train()
    for s in range(steps):
        starts = torch.randint(lo, last, (bs,)).tolist()
        b = {k: v.to(dev) for k, v in get_batch(D, starts, L).items()}
        loss, parts = compute_loss(model, b)
        opt.zero_grad()
        loss.backward()
        nn.utils.clip_grad_norm_(model.parameters(), 1.0)
        opt.step()
        if s % 50 == 0:
            print(f"  step {s:4d} loss {float(loss):.3f} " + " ".join(f"{k}={v:.3f}" for k, v in parts.items()))


@torch.no_grad()
def evaluate(model, D, tr_hi, lo, hi, L=128, dev="cpu"):
    """Compares against train-only baselines. Lower pinball measures forecast improvement, not tradable edge."""
    model.eval()
    starts = list(range(lo, hi - L - 1 - MAX_H, L))
    if not starts: raise ValueError("Empty evaluation slice")
    qs = torch.tensor(QUANTILES)
    base_q = torch.stack([torch.quantile(D["R"][:tr_hi-h,j],qs) for j,h in enumerate(HORIZONS)]).to(dev)              # [H,Q] unconditional
    freq = {f: torch.bincount(D["tokens"][:tr_hi, i], minlength=N_TOK[f]).float() + 1
            for i, f in enumerate(FIELDS)}
    ce, ce_base, pb, pb_base, cover, n = 0.0, 0.0, 0.0, 0.0, 0.0, 0
    for s in range(0, len(starts), 16):
        b = {k: v.to(dev) for k, v in get_batch(D, starts[s:s + 16], L).items()}
        out = model(b["x"])
        for i, f in enumerate(FIELDS):
            ce += F.cross_entropy(out["fields"][f].reshape(-1, N_TOK[f]), b["y"][..., i].reshape(-1)).item()
            p = (freq[f] / freq[f].sum()).to(dev)
            ce_base += -torch.log(p[b["y"][..., i]]).mean().item()
        m = (~torch.isnan(b["R"])).float()
        y = torch.nan_to_num(b["R"])
        pb += masked_mean(pinball(out["q"], y), m.unsqueeze(-1)).item()
        pb_base += masked_mean(pinball(base_q.expand_as(out["q"]), y), m.unsqueeze(-1)).item()
        inside = ((y >= out["q"][..., 0]) & (y <= out["q"][..., -1])).float()
        cover += masked_mean(inside, m).item()
        n += 1
    return dict(field_ce=ce / n, field_ce_baseline=ce_base / n, pinball=pb / n,
                pinball_baseline=pb_base / n, coverage_80=cover / n)


def conformal_widen(q_lo, q_hi, y, target=0.8):
    """Split-conformal: widen [q_lo,q_hi] by this amount, fit on a held-out calibration slice."""
    score = torch.maximum(q_lo - y, y - q_hi).flatten()
    if not len(score) or not 0 < target < 1 or not torch.isfinite(score).all(): raise ValueError("Invalid calibration sample")
    rank = math.ceil((len(score) + 1) * target)
    if rank > len(score): return float("inf")
    return max(0., float(torch.sort(score).values[rank-1]))



def walk_forward(N, n_folds=3, min_train_frac=0.5, purge=MAX_H):
    cuts = np.linspace(min_train_frac * N, N, n_folds + 1).astype(int)
    for a, b in zip(cuts[:-1], cuts[1:]):
        yield a, a + purge, b                       # train [0,a), purge gap, val [a+purge,b)


# ----------------------------------------------------------- simulation ----
@torch.no_grad()
def rollout(model, ctx, n_steps=200, n_paths=64, temp=1.0):
    """Sample future event tokens. ctx: [T,5] long. Applies a crude book-validity mask:
    no cancel/modify/trade when the (tracked) resting-order count is zero.
    Replace with a real order book engine before trusting any output."""
    raise RuntimeError("Rollout disabled: no validated order-book engine or token-to-return mapping")
    model.eval()
    x = ctx.unsqueeze(0).repeat(n_paths, 1, 1)
    resting = torch.full((n_paths,), 100.0)
    for _ in range(n_steps):
        out = model(x[:, -model.max_len:])
        new = []
        for f in FIELDS:
            lg = out["fields"][f][:, -1] / temp
            if f == "type":
                empty = resting <= 0
                lg[empty, 0] = lg[empty, 2] = lg[empty, 3] = -1e9
            new.append(torch.multinomial(F.softmax(lg, -1), 1).squeeze(-1))
        new = torch.stack(new, -1)
        t = new[:, 0]
        resting += (t == 1).float() - ((t == 0) | (t == 2)).float()
        x = torch.cat([x, new.unsqueeze(1)], 1)
    return x[:, ctx.size(0):]


def stylized_facts(returns):
    """Check real AND simulated returns: fat tails + volatility clustering."""
    r = np.asarray(returns) - np.mean(returns)
    kurt = np.mean(r ** 4) / np.mean(r ** 2) ** 2 - 3
    a = np.abs(r) - np.abs(r).mean()
    acf = {k: float(np.mean(a[:-k] * a[k:]) / np.mean(a * a)) for k in (1, 10, 50)}
    return dict(excess_kurtosis=float(kurt), abs_return_acf=acf)


# ----------------------------------------------------------------- main ----
if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--steps", type=int, default=300)
    ap.add_argument("--n", type=int, default=200_000)
    a = ap.parse_args()
    dev = "cuda" if torch.cuda.is_available() else "cpu"
    raw = make_synthetic(a.n)
    print("SYNTHETIC smoke test only:", stylized_facts(np.diff(np.log(raw["mid"]))))
    for k, (tr_hi, v_lo, v_hi) in enumerate(walk_forward(a.n)):
        print(f"\nFOLD {k}: train [0,{tr_hi}) | val [{v_lo},{v_hi})")
        D = build_dataset(raw, tr_hi)              # binners/scalers refit per fold, train only
        model = MarketLM().to(dev)
        train(model, D, 0, tr_hi, steps=a.steps, dev=dev)
        res = evaluate(model, D, tr_hi, v_lo, v_hi, dev=dev)
        print({k2: round(v, 4) for k2, v in res.items()})
        print("  forecast-score check only -> pinball < baseline?", res["pinball"] < res["pinball_baseline"],
              "| coverage near 0.80?", round(res["coverage_80"], 3))