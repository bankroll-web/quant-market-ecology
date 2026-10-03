"""
tokenizer_v1.py - tokenize the quant-market-ecology D09 + D09B frozen tapes.

One EVENT = one book-update interval (~27 ms). Each event becomes a group of
small field tokens. Bin edges are fit on TRAIN hours only and re-used as-is on
later hours (no look-ahead). Sequences must not cross episode boundaries.

Run from the repo root:
    python tokenizer_v1.py --repo . --train 3
"""
import argparse
import glob
import os

import numpy as np
import pandas as pd

TICK = 0.1
QLEVELS = [0.2, 0.4, 0.6, 0.8, 0.9, 0.95, 0.99, 0.999]  # fine tail: heavy-tailed sizes
MID_EDGES = np.array([1, 2, 3, 6, 21])  # |ticks|: 0 | 1 | 2 | 3-5 | 6-20 | 21+


# ------------------------------------------------------------------ load ----
def load_hours(repo):
    """Merge D09 (trades + liquidity per interval) with D09B (distance buckets)."""
    out = []
    paths = sorted(glob.glob(os.path.join(repo, "data/frozen/2026-*_d09_joint_flow_liquidity_tape.csv")))
    for p in paths:
        hour = os.path.basename(p)[:13]
        a = pd.read_csv(p)
        b = pd.read_csv(p.replace("d09_joint_flow_liquidity_tape", "d09b_touch_distance_book_events"))
        b = b.drop(columns=[c for c in b.columns if c in a.columns and c != "episode_id"])
        m = a.merge(b, left_on=["episode_id", "t1_event_time_ms"],
                    right_on=["episode_id", "event_time_ms"], how="inner", validate="1:1")
        assert len(m) == len(a), f"{hour}: merge dropped rows"
        m["hour"] = hour
        out.append(m.sort_values(["episode_id", "t1_event_time_ms"]).reset_index(drop=True))
    return out


# ---------------------------------------------------------------- binning ----
class MagBinner:
    """Token 0 = zero/none. Tokens 1..NQ = quantile bins of |x| (train only).
    signed=True doubles the range: 1..NQ negative, NQ+1..2NQ positive."""
    def __init__(self, signed):
        self.signed = signed

    def fit(self, x):
        mag = np.abs(x[x != 0])
        self.edges = np.unique(np.quantile(mag, QLEVELS)) if len(mag) else np.array([])
        nb = len(self.edges) + 1
        self.centers = np.array([np.mean(mag[np.digitize(mag, self.edges) == i]) if
                                 (np.digitize(mag, self.edges) == i).any() else 0.0 for i in range(nb)])
        self.nb = nb
        self.vocab = 1 + nb * (2 if self.signed else 1)
        return self

    def transform(self, x):
        b = np.digitize(np.abs(x), self.edges)               # 0..nb-1
        tok = 1 + b
        if self.signed:
            tok = np.where(x < 0, tok, tok + self.nb)
        return np.where(x == 0, 0, tok).astype(np.int64)

    def inverse(self, t):
        t = np.asarray(t)
        if self.signed:
            neg = (t >= 1) & (t <= self.nb)
            idx = np.where(neg, t - 1, t - 1 - self.nb)
            val = self.centers[np.clip(idx, 0, self.nb - 1)] * np.where(neg, -1, 1)
        else:
            val = self.centers[np.clip(t - 1, 0, self.nb - 1)]
        return np.where(t == 0, 0.0, val)


class EdgeBinner:
    """Plain quantile bins (for state variables like order-book imbalance)."""
    def __init__(self, n):
        self.n = n

    def fit(self, x):
        self.edges = np.unique(np.quantile(x, np.linspace(0, 1, self.n + 1)[1:-1]))
        self.vocab = len(self.edges) + 1
        return self

    def transform(self, x):
        return np.digitize(x, self.edges).astype(np.int64)


NTR_EDGES = np.array([1, 2, 3, 6, 11, 31])   # 0 | 1 | 2 | 3-5 | 6-10 | 11-30 | 31+


def features(df):
    """Raw numeric view of each field (what the tokens are meant to represent)."""
    f = pd.DataFrame(index=df.index)
    f["dt"] = df["interval_ms"].astype(float)
    f["ntr"] = df["n_trades"].astype(float)
    f["flow"] = df["signed_flow_qty"].astype(float)
    f["bid_add"], f["bid_rem"] = df["bid_add_0_5_qty"], df["bid_remove_0_5_qty"]
    f["ask_add"], f["ask_rem"] = df["ask_add_0_5_qty"], df["ask_remove_0_5_qty"]
    f["bid_deep"] = df["bid_net_6_20_qty"] + df["bid_net_gt20_qty"]
    f["ask_deep"] = df["ask_net_6_20_qty"] + df["ask_net_gt20_qty"]
    f["mid"] = np.round(df["mid_change"] / TICK)                      # ticks, event outcome
    f["obi"] = df["obi5_t0"]                                          # state BEFORE the event
    f["wide"] = (df["spread_t0"] / TICK > 1.5).astype(float)
    return f


SPEC = dict(  # field -> (kind, signed)
    dt=("edge", None), ntr=("ntr", None), flow=("mag", True),
    bid_add=("mag", False), bid_rem=("mag", False), ask_add=("mag", False), ask_rem=("mag", False),
    bid_deep=("mag", True), ask_deep=("mag", True), mid=("mid", None), obi=("edge", None), wide=("flag", None),
)


class MarketTokenizer:
    def fit(self, df):
        f = features(df)
        self.b = {}
        for k, (kind, signed) in SPEC.items():
            if kind == "mag":
                self.b[k] = MagBinner(signed).fit(f[k].values)
            elif kind == "edge":
                self.b[k] = EdgeBinner(8 if k == "obi" else 6).fit(f[k].values)
        fixed = dict(ntr=len(NTR_EDGES) + 1, mid=11, wide=2)
        self.vocab = {k: (self.b[k].vocab if k in self.b else fixed[k]) for k in SPEC}
        return self

    def transform(self, df):
        f = features(df)
        cols = {}
        for k, (kind, _) in SPEC.items():
            x = f[k].values
            if k in self.b:
                cols[k] = self.b[k].transform(x)
            elif kind == "ntr":
                cols[k] = np.searchsorted(NTR_EDGES, x, side="right").astype(np.int64)
            elif kind == "mid":
                idx = np.searchsorted(MID_EDGES, np.abs(x), side="right")      # 0..5
                cols[k] = np.where(x == 0, 0, np.where(x < 0, idx, idx + 5)).astype(np.int64)
            else:
                cols[k] = x.astype(np.int64)
        return pd.DataFrame(cols), df["episode_id"].values


# ------------------------------------------------------------------ tests ----
def entropy_bits(counts):
    p = counts / counts.sum()
    p = p[p > 0]
    return float(-(p * np.log2(p)).sum())


def psi(train_tok, test_tok, v):
    a = np.bincount(train_tok, minlength=v) + 1.0
    b = np.bincount(test_tok, minlength=v) + 1.0
    a, b = a / a.sum(), b / b.sum()
    return float(((a - b) * np.log(a / b)).sum())


def bigram_gain(tok_tr, ep_tr, tok_te, ep_te, v):
    """Cross-entropy (bits) of next token: marginal vs conditioned on previous token.
    Fit on train, scored on test, never crossing episode boundaries."""
    def pairs(t, e):
        ok = e[1:] == e[:-1]
        return t[:-1][ok], t[1:][ok]
    p0, n0 = pairs(tok_tr, ep_tr)
    p1, n1 = pairs(tok_te, ep_te)
    marg = (np.bincount(n0, minlength=v) + 1.0)
    marg /= marg.sum()
    joint = np.ones((v, v))
    np.add.at(joint, (p0, n0), 1.0)
    cond = joint / joint.sum(1, keepdims=True)
    return float(-np.log2(marg[n1]).mean()), float(-np.log2(cond[p1, n1]).mean())


def main(repo, n_train):
    hours = load_hours(repo)
    train_df = pd.concat(hours[:n_train], ignore_index=True)
    test_df = pd.concat(hours[n_train:], ignore_index=True)
    # make episode ids unique across hours
    for d in (train_df, test_df):
        d["episode_id"] = d["hour"] + "_" + d["episode_id"].astype(str)
    tk = MarketTokenizer().fit(train_df)
    Xtr, etr = tk.transform(train_df)
    Xte, ete = tk.transform(test_df)
    print(f"train events {len(Xtr):,} (hours: {[h['hour'].iloc[0] for h in hours[:n_train]]})")
    print(f"test  events {len(Xte):,} (hours: {[h['hour'].iloc[0] for h in hours[n_train:]]})")
    print(f"\n{'field':9s} {'vocab':>5s} {'H_train':>8s} {'PSI':>7s} {'CE_marg':>8s} {'CE_prev':>8s} {'gain':>6s}")
    for k in SPEC:
        v = tk.vocab[k]
        h = entropy_bits(np.bincount(Xtr[k].values, minlength=v).astype(float))
        ps = psi(Xtr[k].values, Xte[k].values, v)
        cm, cc = bigram_gain(Xtr[k].values, etr, Xte[k].values, ete, v)
        print(f"{k:9s} {v:5d} {h:8.2f} {ps:7.3f} {cm:8.3f} {cc:8.3f} {cm - cc:6.3f}")
    # reconstruction on TEST (inverse of the tokens vs the true numbers)
    ft = features(test_df)
    print("\nreconstruction on test (decoded vs true):")
    for k in ("flow", "bid_add", "bid_rem", "ask_add", "ask_rem", "bid_deep", "ask_deep"):
        dec = tk.b[k].inverse(Xte[k].values)
        true = ft[k].values
        corr = np.corrcoef(dec, true)[0, 1]
        print(f"  {k:9s} corr={corr:.3f}  sum_true={true.sum():10.2f}  sum_decoded={dec.sum():10.2f}")
    print("\nmid-move token shares on test (0=none, 1-5 down, 6-10 up; buckets 1,2,3-5,6-20,21+ ticks):")
    print(np.round(np.bincount(Xte["mid"].values, minlength=11) / len(Xte), 4))
    print("note: bin edges came from train hours only; PSI > 0.1 means the token distribution drifted.")
    return tk


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--repo", default=".")
    ap.add_argument("--train", type=int, default=3)
    a = ap.parse_args()
    main(a.repo, a.train)
