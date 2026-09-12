import pandas as pd
import numpy as np
from pathlib import Path

ROOT = Path(r"C:\Users\USER\Documents")
REP = ROOT / "EXP01_REPLICATION"

HOURS = [
    "2026-05-25_04",
    "2026-05-25_12",
    "2026-05-25_18",
    "2026-05-26_15",
    "2026-05-26_21",
]

HORIZONS = [1, 3, 5, 10]

OUT_ROWS = REP / "exp01_replication_canonical_rows.csv"
OUT_HOUR = REP / "exp01_replication_hour_summary.csv"
OUT_EP = REP / "exp01_replication_equal_episode_effects.csv"
OUT_SUM = REP / "exp01_replication_final_summary.csv"

print("=" * 124)
print("EXP-01 - FROZEN INDEPENDENT REPLICATION")
print("ABSORPTION VS YIELDING")
print("=" * 124)

print()
print("PRIMARY HORIZONS : H3, H5, H10")
print("DIAGNOSTIC       : H1")
print("NO RETUNING")
print()


# =====================================================================
# BUILD CANONICAL EXP-01 ROWS HOUR BY HOUR
#
# IMPORTANT:
# Future shifts happen on ALL valid intervals first.
# Starting-event filtering happens AFTER the shifts.
# =====================================================================

all_start_rows = []

for hour in HOURS:

    infile = (
        REP
        / f"{hour}_d09b_joint_flow_touch_ecology.csv"
    )

    print()
    print("=" * 124)
    print("BUILDING:", hour)
    print("=" * 124)

    df = pd.read_csv(
        infile
    )

    df["episode_id"] = pd.to_numeric(
        df["episode_id"],
        errors="raise"
    ).astype("int64")

    df["t1_event_time_ms"] = pd.to_numeric(
        df["t1_event_time_ms"],
        errors="raise"
    ).astype("int64")

    df = df.sort_values(
        [
            "episode_id",
            "t1_event_time_ms"
        ]
    ).reset_index(drop=True)

    print(
        "ALL VALID L2 INTERVALS :",
        f"{len(df):,}"
    )

    # -------------------------------------------------------------
    # TRUE CONSECUTIVE L2 FUTURE STATES
    # -------------------------------------------------------------

    for h in HORIZONS:

        df[
            f"future_mid_h{h}"
        ] = (
            df.groupby(
                "episode_id"
            )["mid_t1"]
            .shift(-h)
        )

        df[
            f"future_time_h{h}"
        ] = (
            df.groupby(
                "episode_id"
            )["t1_event_time_ms"]
            .shift(-h)
        )

        df[
            f"future_elapsed_ms_h{h}"
        ] = (
            df[
                f"future_time_h{h}"
            ]
            -
            df[
                "t1_event_time_ms"
            ]
        )

    # -------------------------------------------------------------
    # FROZEN STARTING-EVENT FIREWALL
    # -------------------------------------------------------------

    x = df[
        (
            df[
                "trades_exactly_at_t1"
            ]
            ==
            0
        )
        &
        (
            df[
                "total_flow_qty"
            ]
            >
            0
        )
        &
        (
            df[
                "signed_flow_qty"
            ]
            !=
            0
        )
    ].copy()

    # Unique episode across different hours.
    x["source_hour"] = hour

    x[
        "global_episode_id"
    ] = (
        hour
        +
        "__"
        +
        x[
            "episode_id"
        ].astype(str)
    )

    # -------------------------------------------------------------
    # FLOW STATE
    # -------------------------------------------------------------

    x["flow_sign"] = np.sign(
        x["signed_flow_qty"]
    ).astype(int)

    x["flow_side"] = np.where(
        x["flow_sign"] > 0,
        "BUY",
        "SELL"
    )

    x["flow_magnitude"] = np.abs(
        x["signed_flow_qty"]
    )

    x["flow_purity"] = (
        x["flow_magnitude"]
        /
        x["total_flow_qty"]
    )

    # -------------------------------------------------------------
    # OPPOSING 0-5 TICK LIQUIDITY
    # -------------------------------------------------------------

    x[
        "opposing_near_net_qty"
    ] = np.where(
        x["flow_sign"] > 0,
        x["ask_net_0_5_qty"],
        x["bid_net_0_5_qty"]
    )

    x[
        "opposing_near_add_qty"
    ] = np.where(
        x["flow_sign"] > 0,
        x["ask_add_0_5_qty"],
        x["bid_add_0_5_qty"]
    )

    x[
        "opposing_near_remove_qty"
    ] = np.where(
        x["flow_sign"] > 0,
        x["ask_remove_0_5_qty"],
        x["bid_remove_0_5_qty"]
    )

    x[
        "opposing_depth_t0"
    ] = np.where(
        x["flow_sign"] > 0,
        x["ask_depth5_t0"],
        x["bid_depth5_t0"]
    )

    # -------------------------------------------------------------
    # FROZEN RESPONSE CLASSIFICATION
    # -------------------------------------------------------------

    x[
        "liquidity_response"
    ] = np.select(
        [
            x[
                "opposing_near_net_qty"
            ] > 0,

            x[
                "opposing_near_net_qty"
            ] < 0
        ],
        [
            "REPLENISHMENT",
            "DEPLETION"
        ],
        default="NEUTRAL"
    )

    # -------------------------------------------------------------
    # SAME-INTERVAL RESPONSE
    # -------------------------------------------------------------

    x[
        "directional_same_interval_bps"
    ] = (
        x["flow_sign"]
        *
        x["mid_change_bps"]
    )

    # -------------------------------------------------------------
    # TRUE FUTURE DIRECTIONAL RESPONSE
    # -------------------------------------------------------------

    for h in HORIZONS:

        x[
            f"future_directional_bps_h{h}"
        ] = (
            x["flow_sign"]
            *
            10000.0
            *
            (
                x[
                    f"future_mid_h{h}"
                ]
                -
                x["mid_t1"]
            )
            /
            x["mid_t1"]
        )

    print(
        "CANONICAL START EVENTS :",
        f"{len(x):,}"
    )

    print(
        "BUY                    :",
        f"{int((x['flow_side'] == 'BUY').sum()):,}"
    )

    print(
        "SELL                   :",
        f"{int((x['flow_side'] == 'SELL').sum()):,}"
    )

    print()
    print(
        x[
            "liquidity_response"
        ]
        .value_counts()
        .to_string()
    )

    print()
    print("HORIZON TIMING")

    for h in HORIZONS:

        s = x[
            f"future_elapsed_ms_h{h}"
        ].dropna()

        print(
            f"H{h}: "
            f"n={len(s):,}  "
            f"mean={s.mean():.3f}ms  "
            f"median={s.median():.3f}ms  "
            f"p99={s.quantile(.99):.3f}ms  "
            f"max={s.max():.3f}ms"
        )

    all_start_rows.append(
        x
    )


rows = pd.concat(
    all_start_rows,
    ignore_index=True
)

rows.to_csv(
    OUT_ROWS,
    index=False
)


# =====================================================================
# OVERALL SAMPLE
# =====================================================================

print()
print("=" * 124)
print("COMBINED UNTOUCHED REPLICATION SAMPLE")
print("=" * 124)

print(
    "STARTING EVENTS:",
    f"{len(rows):,}"
)

print(
    "UNIQUE VERIFIED EPISODES:",
    f"{rows['global_episode_id'].nunique():,}"
)

print()

print(
    rows[
        "flow_side"
    ]
    .value_counts()
    .to_string()
)

print()

print(
    rows[
        "liquidity_response"
    ]
    .value_counts()
    .to_string()
)


# =====================================================================
# RAW DEPLETION MINUS REPLENISHMENT
# =====================================================================

print()
print("=" * 124)
print("RAW DEPLETION MINUS REPLENISHMENT")
print("POSITIVE = FROZEN PROPOSITION SUPPORTED")
print("=" * 124)

for side in [
    "POOLED",
    "BUY",
    "SELL"
]:

    if side == "POOLED":

        d = rows

    else:

        d = rows[
            rows[
                "flow_side"
            ]
            ==
            side
        ]

    dep = d[
        d[
            "liquidity_response"
        ]
        ==
        "DEPLETION"
    ]

    rep = d[
        d[
            "liquidity_response"
        ]
        ==
        "REPLENISHMENT"
    ]

    print()
    print(side)

    print(
        "N depletion:",
        f"{len(dep):,}",
        "N replenishment:",
        f"{len(rep):,}"
    )

    for h in HORIZONS:

        col = (
            f"future_directional_bps_h{h}"
        )

        dv = dep[
            col
        ].dropna()

        rv = rep[
            col
        ].dropna()

        diff = (
            dv.mean()
            -
            rv.mean()
        )

        median_diff = (
            dv.median()
            -
            rv.median()
        )

        move_diff = (
            (dv != 0).mean()
            -
            (rv != 0).mean()
        )

        print(
            f"H{h:2d}  "
            f"dep={dv.mean(): .6f}  "
            f"rep={rv.mean(): .6f}  "
            f"diff={diff: .6f} bps  "
            f"median_diff={median_diff: .6f}  "
            f"move_rate_diff={move_diff: .6f}"
        )


# =====================================================================
# PER-HOUR REPLICATION AUDIT
# =====================================================================

print()
print("=" * 124)
print("PER-HOUR POOLED EFFECT")
print("=" * 124)

hour_rows = []

for hour in HOURS:

    d = rows[
        rows[
            "source_hour"
        ]
        ==
        hour
    ]

    dep = d[
        d[
            "liquidity_response"
        ]
        ==
        "DEPLETION"
    ]

    rep = d[
        d[
            "liquidity_response"
        ]
        ==
        "REPLENISHMENT"
    ]

    r = {
        "hour":
            hour,

        "starting_events":
            len(d),

        "episodes":
            d[
                "global_episode_id"
            ].nunique(),

        "depletion_n":
            len(dep),

        "replenishment_n":
            len(rep)
    }

    print()
    print(hour)

    print(
        "START:",
        f"{len(d):,}",
        "DEP:",
        f"{len(dep):,}",
        "REP:",
        f"{len(rep):,}"
    )

    for h in HORIZONS:

        col = (
            f"future_directional_bps_h{h}"
        )

        dv = dep[
            col
        ].dropna()

        rv = rep[
            col
        ].dropna()

        diff = (
            dv.mean()
            -
            rv.mean()
        )

        r[
            f"h{h}_diff_bps"
        ] = diff

        print(
            f"H{h}: {diff: .6f} bps"
        )

    hour_rows.append(
        r
    )


hour_summary = pd.DataFrame(
    hour_rows
)

hour_summary.to_csv(
    OUT_HOUR,
    index=False
)


# =====================================================================
# FROZEN FLOW MAGNITUDE + STARTING DEPTH CONTROL
# =====================================================================

print()
print("=" * 124)
print("STRATIFIED FLOW / DEPTH CONTROL")
print("=" * 124)

comp = rows[
    rows[
        "liquidity_response"
    ].isin(
        [
            "DEPLETION",
            "REPLENISHMENT"
        ]
    )
].copy()

parts = []

for side, g in comp.groupby(
    "flow_side"
):

    g = g.copy()

    g["flow_bin"] = pd.qcut(
        g[
            "flow_magnitude"
        ].rank(
            method="first"
        ),
        q=5,
        labels=False
    )

    g["depth_bin"] = pd.qcut(
        g[
            "opposing_depth_t0"
        ].rank(
            method="first"
        ),
        q=5,
        labels=False
    )

    parts.append(
        g
    )

comp = pd.concat(
    parts,
    ignore_index=True
)

for h in HORIZONS:

    col = (
        f"future_directional_bps_h{h}"
    )

    cells = []

    for keys, g in comp.groupby(
        [
            "flow_side",
            "flow_bin",
            "depth_bin"
        ]
    ):

        dep = g[
            g[
                "liquidity_response"
            ]
            ==
            "DEPLETION"
        ][
            col
        ].dropna()

        rep = g[
            g[
                "liquidity_response"
            ]
            ==
            "REPLENISHMENT"
        ][
            col
        ].dropna()

        if (
            len(dep) < 3
            or
            len(rep) < 3
        ):

            continue

        diff = (
            dep.mean()
            -
            rep.mean()
        )

        weight = min(
            len(dep),
            len(rep)
        )

        cells.append(
            (
                diff,
                weight
            )
        )

    if not cells:

        print(
            f"H{h}: no usable cells"
        )

        continue

    diffs = np.array(
        [
            z[0]
            for z in cells
        ]
    )

    weights = np.array(
        [
            z[1]
            for z in cells
        ]
    )

    print(
        f"H{h}: "
        f"cells={len(cells):2d}  "
        f"weighted={np.average(diffs, weights=weights): .6f} bps  "
        f"median_cell={np.median(diffs): .6f} bps  "
        f"positive_cell_rate={(diffs > 0).mean():.6f}"
    )


# =====================================================================
# ONE-SIDED AGGRESSION ROBUSTNESS
# =====================================================================

print()
print("=" * 124)
print("ONE-SIDED AGGRESSION ROBUSTNESS")
print("=" * 124)

pure = rows[
    (
        (
            rows[
                "aggressive_buy_qty"
            ]
            >
            0
        )
        &
        (
            rows[
                "aggressive_sell_qty"
            ]
            ==
            0
        )
    )
    |
    (
        (
            rows[
                "aggressive_sell_qty"
            ]
            >
            0
        )
        &
        (
            rows[
                "aggressive_buy_qty"
            ]
            ==
            0
        )
    )
].copy()

print(
    "ONE-SIDED EVENTS:",
    f"{len(pure):,}"
)

for side in [
    "POOLED",
    "BUY",
    "SELL"
]:

    if side == "POOLED":

        d = pure

    else:

        d = pure[
            pure[
                "flow_side"
            ]
            ==
            side
        ]

    dep = d[
        d[
            "liquidity_response"
        ]
        ==
        "DEPLETION"
    ]

    rep = d[
        d[
            "liquidity_response"
        ]
        ==
        "REPLENISHMENT"
    ]

    print()
    print(side)

    for h in HORIZONS:

        col = (
            f"future_directional_bps_h{h}"
        )

        dv = dep[
            col
        ].dropna()

        rv = rep[
            col
        ].dropna()

        if (
            len(dv) == 0
            or
            len(rv) == 0
        ):

            continue

        print(
            f"H{h}: "
            f"dep={dv.mean(): .6f}  "
            f"rep={rv.mean(): .6f}  "
            f"diff={dv.mean() - rv.mean(): .6f} bps"
        )


# =====================================================================
# EQUAL-WEIGHT EPISODE TEST
#
# IMPORTANT:
# global_episode_id prevents episode 1 from different hours being
# incorrectly treated as the same episode.
# =====================================================================

print()
print("=" * 124)
print("EQUAL-WEIGHT EPISODE TEST")
print("ONE VERIFIED EPISODE = ONE VOTE")
print("=" * 124)

ec = rows[
    rows[
        "liquidity_response"
    ].isin(
        [
            "DEPLETION",
            "REPLENISHMENT"
        ]
    )
].copy()

episode_rows = []

for h in HORIZONS:

    col = (
        f"future_directional_bps_h{h}"
    )

    for ep, g in ec.groupby(
        "global_episode_id"
    ):

        dep = g[
            g[
                "liquidity_response"
            ]
            ==
            "DEPLETION"
        ][
            col
        ].dropna()

        rep = g[
            g[
                "liquidity_response"
            ]
            ==
            "REPLENISHMENT"
        ][
            col
        ].dropna()

        if (
            len(dep) == 0
            or
            len(rep) == 0
        ):

            continue

        episode_rows.append({

            "horizon":
                h,

            "global_episode_id":
                ep,

            "effect_bps":
                (
                    dep.mean()
                    -
                    rep.mean()
                ),

            "depletion_n":
                len(dep),

            "replenishment_n":
                len(rep),

            "depletion_mean_bps":
                dep.mean(),

            "replenishment_mean_bps":
                rep.mean()
        })


effects = pd.DataFrame(
    episode_rows
)

effects.to_csv(
    OUT_EP,
    index=False
)


# EXACT EXP-01E SETTINGS

RNG = np.random.default_rng(
    20260911
)

N_BOOT = 20000
N_SIGNFLIP = 20000

summary_rows = []


for h in HORIZONS:

    e = effects[
        effects[
            "horizon"
        ]
        ==
        h
    ][
        "effect_bps"
    ].to_numpy(
        dtype=float
    )

    n = len(e)

    if n == 0:

        print()
        print(
            f"H{h}: NO ELIGIBLE EPISODES"
        )

        continue

    nonzero = e[
        e != 0
    ]

    observed_mean = float(
        np.mean(e)
    )

    observed_median = float(
        np.median(e)
    )

    positive_rate_all = float(
        np.mean(
            e > 0
        )
    )

    negative_rate_all = float(
        np.mean(
            e < 0
        )
    )

    zero_rate = float(
        np.mean(
            e == 0
        )
    )

    if len(nonzero):

        positive_rate_nonzero = float(
            np.mean(
                nonzero > 0
            )
        )

        negative_rate_nonzero = float(
            np.mean(
                nonzero < 0
            )
        )

    else:

        positive_rate_nonzero = np.nan
        negative_rate_nonzero = np.nan


    boot_means = np.empty(
        N_BOOT,
        dtype=float
    )

    for b in range(
        N_BOOT
    ):

        sample = RNG.choice(
            e,
            size=n,
            replace=True
        )

        boot_means[b] = np.mean(
            sample
        )


    ci_low = float(
        np.quantile(
            boot_means,
            0.025
        )
    )

    ci_high = float(
        np.quantile(
            boot_means,
            0.975
        )
    )

    boot_p_positive = float(
        np.mean(
            boot_means > 0
        )
    )


    abs_e = np.abs(
        e
    )

    null_means = np.empty(
        N_SIGNFLIP,
        dtype=float
    )

    for b in range(
        N_SIGNFLIP
    ):

        signs = RNG.choice(
            [-1.0, 1.0],
            size=n,
            replace=True
        )

        null_means[b] = np.mean(
            abs_e
            *
            signs
        )


    randomization_p = float(
        (
            1
            +
            np.sum(
                null_means
                >=
                observed_mean
            )
        )
        /
        (
            N_SIGNFLIP
            +
            1
        )
    )


    # -------------------------------------------------------------
    # EFFECT CONCENTRATION
    # -------------------------------------------------------------

    abs_sorted = np.sort(
        np.abs(e)
    )[::-1]

    total_abs = float(
        abs_sorted.sum()
    )

    concentration = {}

    for frac in [
        0.05,
        0.10,
        0.20
    ]:

        k = max(
            1,
            int(
                np.ceil(
                    n
                    *
                    frac
                )
            )
        )

        share = (
            float(
                abs_sorted[
                    :k
                ].sum()
                /
                total_abs
            )
            if total_abs > 0
            else np.nan
        )

        concentration[
            frac
        ] = share


    print()
    print("-" * 124)
    print(
        f"HORIZON {h}"
    )
    print("-" * 124)

    print(
        "Episodes with both states :",
        f"{n:,}"
    )

    print(
        "Equal-weight mean effect  :",
        f"{observed_mean: .6f} bps"
    )

    print(
        "Episode median effect     :",
        f"{observed_median: .6f} bps"
    )

    print(
        "Positive rate - all       :",
        f"{positive_rate_all:.6f}"
    )

    print(
        "Negative rate - all       :",
        f"{negative_rate_all:.6f}"
    )

    print(
        "Zero rate                 :",
        f"{zero_rate:.6f}"
    )

    print(
        "Positive rate - nonzero   :",
        f"{positive_rate_nonzero:.6f}"
    )

    print(
        "Negative rate - nonzero   :",
        f"{negative_rate_nonzero:.6f}"
    )

    print(
        "Equal-episode bootstrap CI:",
        f"[{ci_low: .6f}, {ci_high: .6f}] bps"
    )

    print(
        "Bootstrap P(mean > 0)     :",
        f"{boot_p_positive:.6f}"
    )

    print(
        "Sign-flip one-sided p     :",
        f"{randomization_p:.6f}"
    )

    print(
        "Top 5% abs-effect share   :",
        f"{concentration[0.05]:.6f}"
    )

    print(
        "Top 10% abs-effect share  :",
        f"{concentration[0.10]:.6f}"
    )

    print(
        "Top 20% abs-effect share  :",
        f"{concentration[0.20]:.6f}"
    )


    summary_rows.append({

        "horizon":
            h,

        "episodes":
            n,

        "equal_weight_mean_bps":
            observed_mean,

        "median_effect_bps":
            observed_median,

        "positive_rate_all":
            positive_rate_all,

        "negative_rate_all":
            negative_rate_all,

        "zero_rate":
            zero_rate,

        "positive_rate_nonzero":
            positive_rate_nonzero,

        "negative_rate_nonzero":
            negative_rate_nonzero,

        "bootstrap_ci_low_bps":
            ci_low,

        "bootstrap_ci_high_bps":
            ci_high,

        "bootstrap_p_mean_positive":
            boot_p_positive,

        "signflip_one_sided_p":
            randomization_p,

        "top5pct_abs_effect_share":
            concentration[0.05],

        "top10pct_abs_effect_share":
            concentration[0.10],

        "top20pct_abs_effect_share":
            concentration[0.20]
    })


final_summary = pd.DataFrame(
    summary_rows
)

final_summary.to_csv(
    OUT_SUM,
    index=False
)


# =====================================================================
# FROZEN REPLICATION VERDICT
#
# H3/H5/H10 are PRIMARY.
#
# We do NOT alter the experiment based on these results.
# =====================================================================

print()
print("=" * 124)
print("FROZEN PRIMARY-HORIZON VERDICT TABLE")
print("=" * 124)

for h in [
    3,
    5,
    10
]:

    r = final_summary[
        final_summary[
            "horizon"
        ]
        ==
        h
    ].iloc[0]

    direction_ok = (
        r[
            "equal_weight_mean_bps"
        ]
        >
        0
    )

    ci_ok = (
        r[
            "bootstrap_ci_low_bps"
        ]
        >
        0
    )

    signflip_ok = (
        r[
            "signflip_one_sided_p"
        ]
        <
        0.05
    )

    status = (
        "SURVIVES"
        if (
            direction_ok
            and
            ci_ok
            and
            signflip_ok
        )
        else
        "DOES NOT SURVIVE"
    )

    print(
        f"H{h}: "
        f"mean={r['equal_weight_mean_bps']: .6f}  "
        f"CI=[{r['bootstrap_ci_low_bps']: .6f}, "
        f"{r['bootstrap_ci_high_bps']: .6f}]  "
        f"signflip_p={r['signflip_one_sided_p']:.6f}  "
        f"=> {status}"
    )


print()
print("SAVED CANONICAL ROWS:")
print(OUT_ROWS)

print()
print("SAVED PER-HOUR SUMMARY:")
print(OUT_HOUR)

print()
print("SAVED EPISODE EFFECTS:")
print(OUT_EP)

print()
print("SAVED FINAL SUMMARY:")
print(OUT_SUM)

print()
print("=" * 124)
print("EXP-01 FROZEN INDEPENDENT REPLICATION COMPLETE")
print("=" * 124)
