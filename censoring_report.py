"""Censoring diagnostics for triple-barrier label attempts.

Question answered: are labels being dropped (gaps, book resets, invalid books)
more often in some market conditions than others? If censoring rises with
volatility, the surviving training set under-represents the hardest moments
and any model trained on it will look better than it should.

Input is one row per label ATTEMPT (including censored ones), not just the
labels that survived. Required columns (names configurable):
    time_col    decision time, integer nanoseconds UTC
    vol_col     volatility known AT decision time (past-only, in bps)
    status_col  'labeled' or anything else (= censored)
    reason_col  why it was censored (free text / enum); ignored if absent
    label_col   +1 / -1 / 0 for labeled rows; NaN for censored rows

Bucket edges are fit on the whole sample here because this is a diagnostic
of the data feed, not a model input. Never reuse these edges as model
features; fit feature bins on each training fold only.
"""
from __future__ import annotations

import math

import numpy as np
import pandas as pd

Z95 = 1.959963984540054
NS_PER_HOUR = 3_600_000_000_000


def wilson_interval(k: int, n: int, z: float = Z95) -> tuple[float, float]:
    """Wilson score interval for a binomial proportion. Returns (low, high)."""
    if n <= 0:
        return (float("nan"), float("nan"))
    p = k / n
    denom = 1.0 + z * z / n
    centre = (p + z * z / (2 * n)) / denom
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / denom
    return (max(0.0, centre - half), min(1.0, centre + half))


def _rate_table(df: pd.DataFrame, group: pd.Series, censored: pd.Series) -> pd.DataFrame:
    rows = []
    for key, idx in df.groupby(group, observed=True).groups.items():
        c = censored.loc[idx]
        n, k = int(len(c)), int(c.sum())
        lo, hi = wilson_interval(k, n)
        rows.append({"group": key, "attempts": n, "censored": k,
                     "censor_rate": k / n if n else float("nan"),
                     "ci_low": lo, "ci_high": hi})
    return pd.DataFrame(rows)


def _censored_runs(censored: pd.Series) -> dict:
    """Consecutive censored attempts in time order = outages, not random noise."""
    runs, cur = [], 0
    for flag in censored.to_numpy():
        if flag:
            cur += 1
        elif cur:
            runs.append(cur)
            cur = 0
    if cur:
        runs.append(cur)
    return {"n_runs": len(runs), "longest_run": max(runs) if runs else 0,
            "median_run": float(np.median(runs)) if runs else 0.0}


def censoring_report(df: pd.DataFrame, *, time_col: str = "decision_ns",
                     vol_col: str = "vol_bps", status_col: str = "status",
                     reason_col: str = "reason", label_col: str = "label",
                     labeled_value: str = "labeled", n_buckets: int = 5,
                     max_overall_censor: float = 0.20) -> dict:
    """Build the report. Returns dict of DataFrames plus a list of text flags."""
    for col in (time_col, vol_col, status_col):
        if col not in df.columns:
            raise KeyError(f"missing required column: {col}")
    d = df.sort_values(time_col).reset_index(drop=True).copy()
    if d[vol_col].isna().any():
        raise ValueError("vol_col has NaN; vol must be known at every decision "
                         "(drop warm-up rows explicitly rather than hiding them)")
    censored = d[status_col] != labeled_value

    d["vol_bucket"] = pd.qcut(d[vol_col], q=n_buckets, duplicates="drop")
    if d["vol_bucket"].isna().all() and len(d):
        d["vol_bucket"] = pd.Categorical(["constant volatility"] * len(d))
    by_vol = _rate_table(d, d["vol_bucket"], censored)

    if label_col in d.columns:
        lab = d[~censored]
        mix = (lab.groupby("vol_bucket", observed=True)[label_col]
               .agg(share_profit=lambda s: float((s == 1).mean()),
                    share_loss=lambda s: float((s == -1).mean()),
                    share_time=lambda s: float((s == 0).mean()),
                    labeled="count").reset_index())
        mix = mix.rename(columns={"vol_bucket": "group"})
        by_vol = by_vol.merge(mix, on="group", how="left")

    hours = ((d[time_col] // NS_PER_HOUR) % 24).astype(int)
    by_hour = _rate_table(d, hours, censored)

    if reason_col in d.columns:
        by_reason = (d[censored].groupby(reason_col).size()
                     .rename("count").reset_index()
                     .sort_values("count", ascending=False))
    else:
        by_reason = pd.DataFrame(columns=[reason_col, "count"])

    runs = _censored_runs(censored)
    overall = float(censored.mean())

    flags = []
    if len(by_vol) >= 2:
        lo_b, hi_b = by_vol.iloc[0], by_vol.iloc[-1]
        if hi_b["ci_low"] > lo_b["ci_high"]:
            flags.append(
                f"CENSORING RISES WITH VOLATILITY: {lo_b['censor_rate']:.1%} in the "
                f"calmest bucket vs {hi_b['censor_rate']:.1%} in the most volatile "
                "(95% intervals do not overlap). Surviving labels under-represent "
                "violent moves.")
        elif lo_b["ci_low"] > hi_b["ci_high"]:
            flags.append(
                f"CENSORING FALLS WITH VOLATILITY: {lo_b['censor_rate']:.1%} calm vs "
                f"{hi_b['censor_rate']:.1%} volatile. Check for quiet-period feed gaps.")
    if overall > max_overall_censor:
        flags.append(f"HIGH OVERALL CENSORING: {overall:.1%} > {max_overall_censor:.0%}.")
    if runs["longest_run"] >= 20:
        flags.append(f"LONG OUTAGE RUN: {runs['longest_run']} consecutive censored "
                     "attempts. Inspect the feed around that window.")

    return {"overall_censor_rate": overall, "attempts": int(len(d)),
            "by_volatility": by_vol, "by_hour_utc": by_hour,
            "by_reason": by_reason, "runs": runs, "flags": flags}


def print_report(rep: dict) -> None:
    print(f"attempts={rep['attempts']}  overall censored={rep['overall_censor_rate']:.1%}")
    print("\nBy volatility bucket (calm -> violent):")
    print(rep["by_volatility"].to_string(index=False, float_format=lambda x: f"{x:.3f}"))
    print("\nBy reason:")
    print(rep["by_reason"].to_string(index=False))
    print(f"\nCensored runs: {rep['runs']}")
    print("\nFLAGS:" if rep["flags"] else "\nNo flags raised.")
    for f in rep["flags"]:
        print(" -", f)
