"""
EXP-01 absorption-vs-yielding analysis layer.

Exact port of the canonical EXP-01 analysis scripts:
  - exp01c_canonical_absorption_yielding.py  (analysis frame + group summary)
  - exp01d_episode_bootstrap.py              (episode-level cluster bootstrap)
  - exp01e_equal_episode_test.py             (equal-weight episode test)
  - exp01_frozen_independent_replication.py  (frozen independent replication)

Behavior is frozen: any refactor must reproduce the frozen
exp01c/exp01d/exp01e/exp01_replication_* CSV files row-for-row.

Canonical temporal convention (do NOT change):
  - future states are computed on ALL valid L2 intervals first
    (groupby-episode shift of the next h-th interval)
  - the starting-event firewall (no trades exactly at t1, positive
    total flow, nonzero signed flow) is applied AFTER the shifts
  - flow sign/opposing liquidity/response classification are derived
    from the d09b joint tape columns

Input note (matches canonical behavior): the d09b joint CSVs are read
with pandas' DEFAULT parser. The frozen exp01 outputs embed the
resulting last-ULP artifacts (ledger O9); reading with
float_precision='round_trip' would NOT reproduce them bit-for-bit.

Replication column-order note: the frozen exp01_replication_canonical_rows.csv
carries `hour` as its FIRST column — the replication hour joint CSVs
already contain `hour` first (written by the canonical D09B replication),
so it flows through the analysis frame untouched. source_hour and
global_episode_id sit between the future-shift columns and the flow-state
columns: the frozen producing script assigned them there, so the
flow-state step is a separate function applied after the episode keys.
"""
import numpy as np
import pandas as pd

HORIZONS = [1, 3, 5, 10]
RNG_SEED = 20260911

RESPONSE_ORDER = ["DEPLETION", "REPLENISHMENT", "NEUTRAL"]
SIDE_ORDER = ["POOLED", "BUY", "SELL"]


# =====================================================================
# ANALYSIS FRAME (exp01c core)
# =====================================================================

def prepare_intervals(df):
    """Cast ids, sort, compute future states on ALL intervals, firewall.

    Returns the starting-event frame x (all original columns plus the
    future_mid/future_time/future_elapsed columns). Flow-state columns
    are added separately by add_flow_state so replication can insert
    source_hour/global_episode_id between the two sections.
    """
    df = df.copy()
    df["episode_id"] = pd.to_numeric(
        df["episode_id"], errors="raise"
    ).astype("int64")
    df["t1_event_time_ms"] = pd.to_numeric(
        df["t1_event_time_ms"], errors="raise"
    ).astype("int64")
    df = df.sort_values(
        ["episode_id", "t1_event_time_ms"]
    ).reset_index(drop=True)

    for h in HORIZONS:
        df[f"future_mid_h{h}"] = (
            df.groupby("episode_id")["mid_t1"].shift(-h)
        )
        df[f"future_time_h{h}"] = (
            df.groupby("episode_id")["t1_event_time_ms"].shift(-h)
        )
        df[f"future_elapsed_ms_h{h}"] = (
            df[f"future_time_h{h}"] - df["t1_event_time_ms"]
        )

    x = df[
        (df["trades_exactly_at_t1"] == 0)
        & (df["total_flow_qty"] > 0)
        & (df["signed_flow_qty"] != 0)
    ].copy()
    return x


def add_flow_state(x):
    """Flow state, opposing near-touch liquidity, response, directional bps."""
    x = x.copy()

    x["flow_sign"] = np.sign(x["signed_flow_qty"]).astype(int)
    x["flow_side"] = np.where(x["flow_sign"] > 0, "BUY", "SELL")
    x["flow_magnitude"] = np.abs(x["signed_flow_qty"])
    x["flow_purity"] = x["flow_magnitude"] / x["total_flow_qty"]

    x["opposing_near_net_qty"] = np.where(
        x["flow_sign"] > 0,
        x["ask_net_0_5_qty"],
        x["bid_net_0_5_qty"],
    )
    x["opposing_near_add_qty"] = np.where(
        x["flow_sign"] > 0,
        x["ask_add_0_5_qty"],
        x["bid_add_0_5_qty"],
    )
    x["opposing_near_remove_qty"] = np.where(
        x["flow_sign"] > 0,
        x["ask_remove_0_5_qty"],
        x["bid_remove_0_5_qty"],
    )
    x["opposing_depth_t0"] = np.where(
        x["flow_sign"] > 0,
        x["ask_depth5_t0"],
        x["bid_depth5_t0"],
    )

    x["liquidity_response"] = np.select(
        [
            x["opposing_near_net_qty"] > 0,
            x["opposing_near_net_qty"] < 0,
        ],
        [
            "REPLENISHMENT",
            "DEPLETION",
        ],
        default="NEUTRAL",
    )

    x["directional_same_interval_bps"] = (
        x["flow_sign"] * x["mid_change_bps"]
    )

    for h in HORIZONS:
        x[f"future_directional_bps_h{h}"] = (
            x["flow_sign"]
            * 10000.0
            * (x[f"future_mid_h{h}"] - x["mid_t1"])
            / x["mid_t1"]
        )

    return x


def build_analysis_frame(df):
    """exp01c: prepare intervals + flow state (discovery analysis frame)."""
    return add_flow_state(prepare_intervals(df))


# =====================================================================
# GROUP SUMMARY (exp01c output)
# =====================================================================

def group_summary(x):
    """exp01c group summary: side x response cells with horizon stats."""
    summary_rows = []

    for side in SIDE_ORDER:
        if side == "POOLED":
            d = x
        else:
            d = x[x["flow_side"] == side]

        for response in RESPONSE_ORDER:
            g = d[d["liquidity_response"] == response]
            if len(g) == 0:
                continue

            row = {
                "flow_side": side,
                "liquidity_response": response,
                "n": len(g),
                "median_flow_magnitude": g["flow_magnitude"].median(),
                "median_opposing_depth": g["opposing_depth_t0"].median(),
                "mean_flow_purity": g["flow_purity"].mean(),
                "same_interval_mean_bps": g["directional_same_interval_bps"].mean(),
                "same_interval_positive_rate": (
                    g["directional_same_interval_bps"] > 0
                ).mean(),
            }

            for h in HORIZONS:
                col = f"future_directional_bps_h{h}"
                v = g[col].dropna()
                row[f"h{h}_n"] = len(v)
                row[f"h{h}_mean_bps"] = v.mean()
                row[f"h{h}_median_bps"] = v.median()
                row[f"h{h}_positive_rate"] = (v > 0).mean()
                row[f"h{h}_nonzero_rate"] = (v != 0).mean()
                nz = v[v != 0]
                row[f"h{h}_mean_given_move_bps"] = (
                    nz.mean() if len(nz) else np.nan
                )

            summary_rows.append(row)

    return pd.DataFrame(summary_rows)


# =====================================================================
# DIAGNOSTIC SECTIONS (print-only in canonical; returned as frames)
# =====================================================================

def raw_differences(x):
    """Raw depletion-minus-replenishment per side and horizon."""
    rows = []
    for side in SIDE_ORDER:
        if side == "POOLED":
            d = x
        else:
            d = x[x["flow_side"] == side]
        dep = d[d["liquidity_response"] == "DEPLETION"]
        rep = d[d["liquidity_response"] == "REPLENISHMENT"]
        for h in HORIZONS:
            col = f"future_directional_bps_h{h}"
            dv = dep[col].dropna()
            rv = rep[col].dropna()
            rows.append({
                "flow_side": side,
                "horizon": h,
                "depletion_n": len(dv),
                "replenishment_n": len(rv),
                "depletion_mean_bps": dv.mean(),
                "replenishment_mean_bps": rv.mean(),
                "mean_diff_bps": dv.mean() - rv.mean(),
                "median_diff_bps": dv.median() - rv.median(),
                "move_rate_diff": (dv != 0).mean() - (rv != 0).mean(),
            })
    return pd.DataFrame(rows)


def stratified_control(x):
    """Flow-magnitude x starting-depth quintile control (per side)."""
    comp = x[
        x["liquidity_response"].isin(["DEPLETION", "REPLENISHMENT"])
    ].copy()

    parts = []
    for _side, g in comp.groupby("flow_side"):
        g = g.copy()
        g["flow_bin"] = pd.qcut(
            g["flow_magnitude"].rank(method="first"), q=5, labels=False
        )
        g["depth_bin"] = pd.qcut(
            g["opposing_depth_t0"].rank(method="first"), q=5, labels=False
        )
        parts.append(g)
    comp = pd.concat(parts, ignore_index=True)

    rows = []
    for h in HORIZONS:
        col = f"future_directional_bps_h{h}"
        cells = []
        for _keys, g in comp.groupby(["flow_side", "flow_bin", "depth_bin"]):
            dep = g[g["liquidity_response"] == "DEPLETION"][col].dropna()
            rep = g[g["liquidity_response"] == "REPLENISHMENT"][col].dropna()
            if len(dep) < 3 or len(rep) < 3:
                continue
            cells.append((dep.mean() - rep.mean(), min(len(dep), len(rep))))
        if not cells:
            rows.append({
                "horizon": h, "cells": 0,
                "weighted_diff_bps": np.nan,
                "median_cell_diff_bps": np.nan,
                "positive_cell_rate": np.nan,
            })
            continue
        diffs = np.array([z[0] for z in cells])
        weights = np.array([z[1] for z in cells])
        rows.append({
            "horizon": h,
            "cells": len(cells),
            "weighted_diff_bps": np.average(diffs, weights=weights),
            "median_cell_diff_bps": np.median(diffs),
            "positive_cell_rate": (diffs > 0).mean(),
        })
    return pd.DataFrame(rows)


def one_sided_robustness(x):
    """Depletion-vs-replenishment restricted to one-sided aggression."""
    pure = x[
        (
            (x["aggressive_buy_qty"] > 0)
            & (x["aggressive_sell_qty"] == 0)
        )
        | (
            (x["aggressive_sell_qty"] > 0)
            & (x["aggressive_buy_qty"] == 0)
        )
    ].copy()

    rows = []
    for side in SIDE_ORDER:
        if side == "POOLED":
            d = pure
        else:
            d = pure[pure["flow_side"] == side]
        dep = d[d["liquidity_response"] == "DEPLETION"]
        rep = d[d["liquidity_response"] == "REPLENISHMENT"]
        for h in HORIZONS:
            col = f"future_directional_bps_h{h}"
            dv = dep[col].dropna()
            rv = rep[col].dropna()
            if len(dv) == 0 or len(rv) == 0:
                continue
            rows.append({
                "flow_side": side,
                "horizon": h,
                "depletion_mean_bps": dv.mean(),
                "replenishment_mean_bps": rv.mean(),
                "diff_bps": dv.mean() - rv.mean(),
            })
    return pd.DataFrame(rows)


# =====================================================================
# EPISODE-LEVEL BOOTSTRAP (exp01d output)
# =====================================================================

def episode_bootstrap(x, n_boot=10000, seed=RNG_SEED):
    """Cluster bootstrap resampling whole episodes (exp01d).

    Exact port: one bootstrap draw = one resample of the full episode
    inventory with replacement; duplicated episodes stay duplicated.
    """
    x = x[
        x["liquidity_response"].isin(["DEPLETION", "REPLENISHMENT"])
    ].copy()

    observed = {}
    for h in HORIZONS:
        col = f"future_directional_bps_h{h}"
        dep = x[x["liquidity_response"] == "DEPLETION"][col].dropna()
        rep = x[x["liquidity_response"] == "REPLENISHMENT"][col].dropna()
        observed[h] = dep.mean() - rep.mean()

    episode_ids = np.array(sorted(x["episode_id"].unique()))
    episode_frames = {
        ep: x[x["episode_id"] == ep].copy() for ep in episode_ids
    }
    n_episodes = len(episode_ids)

    rng = np.random.default_rng(seed)
    boot = {h: [] for h in HORIZONS}

    for _b in range(n_boot):
        sampled_ids = rng.choice(episode_ids, size=n_episodes, replace=True)
        pieces = [episode_frames[ep] for ep in sampled_ids]
        sample = pd.concat(pieces, ignore_index=True)
        for h in HORIZONS:
            col = f"future_directional_bps_h{h}"
            dep = sample[sample["liquidity_response"] == "DEPLETION"][col].dropna()
            rep = sample[sample["liquidity_response"] == "REPLENISHMENT"][col].dropna()
            if len(dep) == 0 or len(rep) == 0:
                continue
            boot[h].append(dep.mean() - rep.mean())

    rows = []
    for h in HORIZONS:
        arr = np.asarray(boot[h], dtype=float)
        rows.append({
            "horizon_events": h,
            "observed_diff_bps": observed[h],
            "bootstrap_mean_bps": np.mean(arr),
            "bootstrap_median_bps": np.median(arr),
            "ci_2_5_bps": np.quantile(arr, 0.025),
            "ci_97_5_bps": np.quantile(arr, 0.975),
            "p_diff_positive": np.mean(arr > 0),
            "p_diff_nonpositive": np.mean(arr <= 0),
            "bootstrap_draws": len(arr),
        })
    return pd.DataFrame(rows)


def episode_contribution_audit(x):
    """Per-horizon within-episode effect distribution (print-only)."""
    x = x[
        x["liquidity_response"].isin(["DEPLETION", "REPLENISHMENT"])
    ].copy()

    rows = []
    for h in HORIZONS:
        col = f"future_directional_bps_h{h}"
        episode_effects = []
        for ep, g in x.groupby("episode_id"):
            dep = g[g["liquidity_response"] == "DEPLETION"][col].dropna()
            rep = g[g["liquidity_response"] == "REPLENISHMENT"][col].dropna()
            if len(dep) == 0 or len(rep) == 0:
                continue
            episode_effects.append(
                (int(ep), dep.mean() - rep.mean(), len(dep), len(rep))
            )
        if not episode_effects:
            rows.append({
                "horizon": h, "episodes": 0,
                "median_effect_bps": np.nan,
                "positive_rate": np.nan,
                "p25_bps": np.nan,
                "p75_bps": np.nan,
            })
            continue
        effects = np.array([z[1] for z in episode_effects], dtype=float)
        rows.append({
            "horizon": h,
            "episodes": len(effects),
            "median_effect_bps": np.median(effects),
            "positive_rate": np.mean(effects > 0),
            "p25_bps": np.quantile(effects, 0.25),
            "p75_bps": np.quantile(effects, 0.75),
        })
    return pd.DataFrame(rows)


# =====================================================================
# EQUAL-WEIGHT EPISODE TEST (exp01e output + replication variant)
# =====================================================================

def equal_episode_effects(x, episode_key="episode_id"):
    """Within-episode depletion-minus-replenishment effects (exp01e)."""
    x = x[
        x["liquidity_response"].isin(["DEPLETION", "REPLENISHMENT"])
    ].copy()

    episode_rows = []
    for h in HORIZONS:
        col = f"future_directional_bps_h{h}"
        for ep, g in x.groupby(episode_key):
            dep = g[g["liquidity_response"] == "DEPLETION"][col].dropna()
            rep = g[g["liquidity_response"] == "REPLENISHMENT"][col].dropna()
            if len(dep) == 0 or len(rep) == 0:
                continue
            episode_rows.append({
                "horizon": h,
                episode_key: int(ep) if episode_key == "episode_id" else ep,
                "effect_bps": dep.mean() - rep.mean(),
                "depletion_n": len(dep),
                "replenishment_n": len(rep),
                "depletion_mean_bps": dep.mean(),
                "replenishment_mean_bps": rep.mean(),
            })
    return pd.DataFrame(episode_rows)


def equal_episode_summary(
    effects,
    episode_col,
    n_boot=20000,
    n_signflip=20000,
    seed=RNG_SEED,
    include_concentration=False,
):
    """Equal-weight episode bootstrap + sign-flip test (exp01e summary).

    include_concentration=True adds the top-5/10/20% absolute-effect
    shares to the summary (frozen replication final summary).
    """
    rng = np.random.default_rng(seed)
    summary_rows = []

    for h in HORIZONS:
        e = effects[effects["horizon"] == h]["effect_bps"].to_numpy(dtype=float)
        n = len(e)
        if n == 0:
            continue

        nonzero = e[e != 0]
        observed_mean = np.mean(e)
        observed_median = np.median(e)
        positive_rate_all = np.mean(e > 0)
        negative_rate_all = np.mean(e < 0)
        zero_rate = np.mean(e == 0)
        if len(nonzero):
            positive_rate_nonzero = np.mean(nonzero > 0)
            negative_rate_nonzero = np.mean(nonzero < 0)
        else:
            positive_rate_nonzero = np.nan
            negative_rate_nonzero = np.nan

        boot_means = np.empty(n_boot, dtype=float)
        for b in range(n_boot):
            sample = rng.choice(e, size=n, replace=True)
            boot_means[b] = np.mean(sample)
        ci_low = np.quantile(boot_means, 0.025)
        ci_high = np.quantile(boot_means, 0.975)
        boot_p_positive = np.mean(boot_means > 0)

        abs_e = np.abs(e)
        null_means = np.empty(n_signflip, dtype=float)
        for b in range(n_signflip):
            signs = rng.choice([-1.0, 1.0], size=n, replace=True)
            null_means[b] = np.mean(abs_e * signs)

        # One-sided test: frozen proposition is depletion > replenishment.
        randomization_p = (
            1 + np.sum(null_means >= observed_mean)
        ) / (n_signflip + 1)

        row = {
            "horizon": h,
            "episodes": n,
            "equal_weight_mean_bps": observed_mean,
            "median_effect_bps": observed_median,
            "positive_rate_all": positive_rate_all,
            "negative_rate_all": negative_rate_all,
            "zero_rate": zero_rate,
            "positive_rate_nonzero": positive_rate_nonzero,
            "negative_rate_nonzero": negative_rate_nonzero,
            "bootstrap_ci_low_bps": ci_low,
            "bootstrap_ci_high_bps": ci_high,
            "bootstrap_p_mean_positive": boot_p_positive,
            "signflip_one_sided_p": randomization_p,
        }

        if include_concentration:
            abs_sorted = np.sort(np.abs(e))[::-1]
            total_abs = float(abs_sorted.sum())
            for frac in [0.05, 0.10, 0.20]:
                k = max(1, int(np.ceil(n * frac)))
                share = (
                    float(abs_sorted[:k].sum() / total_abs)
                    if total_abs > 0
                    else np.nan
                )
                row[f"top{int(frac * 100)}pct_abs_effect_share"] = share

        summary_rows.append(row)

    return pd.DataFrame(summary_rows)


# =====================================================================
# FROZEN INDEPENDENT REPLICATION
# =====================================================================

def build_replication_rows(hour_dfs):
    """Per-hour analysis frames with source_hour/global_episode_id.

    hour_dfs: ordered mapping {hour_label: d09b joint DataFrame read with
    the DEFAULT parser}. The replication hour joint CSVs already carry
    `hour` as their FIRST column (written by the canonical D09B
    replication), so it flows through prepare_intervals untouched;
    source_hour/global_episode_id are assigned between the future-shift
    section and the flow-state section, matching the frozen
    exp01_replication_canonical_rows.csv column order.
    """
    all_start_rows = []
    for hour, df in hour_dfs.items():
        x = prepare_intervals(df)
        x["source_hour"] = hour
        x["global_episode_id"] = hour + "__" + x["episode_id"].astype(str)
        x = add_flow_state(x)
        all_start_rows.append(x)
    return pd.concat(all_start_rows, ignore_index=True)


def per_hour_summary(rows, hours):
    """Per-hour pooled depletion-minus-replenishment effects."""
    hour_rows = []
    for hour in hours:
        d = rows[rows["source_hour"] == hour]
        dep = d[d["liquidity_response"] == "DEPLETION"]
        rep = d[d["liquidity_response"] == "REPLENISHMENT"]
        r = {
            "hour": hour,
            "starting_events": len(d),
            "episodes": d["global_episode_id"].nunique(),
            "depletion_n": len(dep),
            "replenishment_n": len(rep),
        }
        for h in HORIZONS:
            col = f"future_directional_bps_h{h}"
            dv = dep[col].dropna()
            rv = rep[col].dropna()
            r[f"h{h}_diff_bps"] = dv.mean() - rv.mean()
        hour_rows.append(r)
    return pd.DataFrame(hour_rows)


def replication_verdict(final_summary):
    """Primary-horizon (H3/H5/H10) survival verdict (print-only)."""
    rows = []
    for h in [3, 5, 10]:
        r = final_summary[final_summary["horizon"] == h].iloc[0]
        direction_ok = r["equal_weight_mean_bps"] > 0
        ci_ok = r["bootstrap_ci_low_bps"] > 0
        signflip_ok = r["signflip_one_sided_p"] < 0.05
        status = (
            "SURVIVES"
            if direction_ok and ci_ok and signflip_ok
            else "DOES NOT SURVIVE"
        )
        rows.append({
            "horizon": h,
            "equal_weight_mean_bps": r["equal_weight_mean_bps"],
            "bootstrap_ci_low_bps": r["bootstrap_ci_low_bps"],
            "bootstrap_ci_high_bps": r["bootstrap_ci_high_bps"],
            "signflip_one_sided_p": r["signflip_one_sided_p"],
            "status": status,
        })
    return pd.DataFrame(rows)