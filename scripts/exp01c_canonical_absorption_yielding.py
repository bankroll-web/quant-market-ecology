import pandas as pd
import numpy as np
from pathlib import Path

INFILE = Path(
    r"C:\Users\USER\Documents\d09b_joint_flow_touch_ecology.csv"
)

OUTFILE = Path(
    r"C:\Users\USER\Documents\exp01c_canonical_rows.csv"
)

SUMMARY_OUT = Path(
    r"C:\Users\USER\Documents\exp01c_canonical_summary.csv"
)

print("=" * 122)
print("EXP-01C - CANONICAL ABSORPTION VS YIELDING")
print("TRUE CONSECUTIVE L2 FUTURE HORIZONS")
print("=" * 122)


# =====================================================================
# LOAD ALL VALID INTERVALS
# =====================================================================

df = pd.read_csv(INFILE)

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

print()
print(
    "ALL VALID L2 INTERVALS:",
    f"{len(df):,}"
)


# =====================================================================
# CRITICAL FIX
#
# Compute future states using ALL valid L2 intervals FIRST.
#
# We exclude timestamp-ambiguous events only when choosing the STARTING
# flow event. Future midpoint observations themselves remain valid.
# =====================================================================

HORIZONS = [
    1,
    3,
    5,
    10
]

for h in HORIZONS:

    df[
        f"future_mid_h{h}"
    ] = (
        df.groupby("episode_id")["mid_t1"]
        .shift(-h)
    )

    df[
        f"future_time_h{h}"
    ] = (
        df.groupby("episode_id")["t1_event_time_ms"]
        .shift(-h)
    )

    df[
        f"future_elapsed_ms_h{h}"
    ] = (
        df[f"future_time_h{h}"]
        -
        df["t1_event_time_ms"]
    )


# =====================================================================
# STARTING-EVENT FIREWALL
# =====================================================================

x = df[
    (df["trades_exactly_at_t1"] == 0)
    &
    (df["total_flow_qty"] > 0)
    &
    (df["signed_flow_qty"] != 0)
].copy()


print(
    "CANONICAL STARTING FLOW EVENTS:",
    f"{len(x):,}"
)


# =====================================================================
# FLOW STATE
# =====================================================================

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


# =====================================================================
# OPPOSING NEAR-TOUCH LIQUIDITY
# =====================================================================

x["opposing_near_net_qty"] = np.where(
    x["flow_sign"] > 0,
    x["ask_net_0_5_qty"],
    x["bid_net_0_5_qty"]
)

x["opposing_near_add_qty"] = np.where(
    x["flow_sign"] > 0,
    x["ask_add_0_5_qty"],
    x["bid_add_0_5_qty"]
)

x["opposing_near_remove_qty"] = np.where(
    x["flow_sign"] > 0,
    x["ask_remove_0_5_qty"],
    x["bid_remove_0_5_qty"]
)

x["opposing_depth_t0"] = np.where(
    x["flow_sign"] > 0,
    x["ask_depth5_t0"],
    x["bid_depth5_t0"]
)


# =====================================================================
# FROZEN RESPONSE CLASSIFICATION
# =====================================================================

x["liquidity_response"] = np.select(
    [
        x["opposing_near_net_qty"] > 0,
        x["opposing_near_net_qty"] < 0
    ],
    [
        "REPLENISHMENT",
        "DEPLETION"
    ],
    default="NEUTRAL"
)


# =====================================================================
# CONTEMPORANEOUS DIRECTIONAL RESPONSE
# =====================================================================

x["directional_same_interval_bps"] = (
    x["flow_sign"]
    *
    x["mid_change_bps"]
)


# =====================================================================
# TRUE CONSECUTIVE-L2 FORWARD RESPONSE
# =====================================================================

for h in HORIZONS:

    x[
        f"future_directional_bps_h{h}"
    ] = (
        x["flow_sign"]
        *
        10000.0
        *
        (
            x[f"future_mid_h{h}"]
            -
            x["mid_t1"]
        )
        /
        x["mid_t1"]
    )


# =====================================================================
# TIMING AUDIT
# =====================================================================

print()
print("=" * 122)
print("TRUE CONSECUTIVE L2 HORIZON AUDIT")
print("=" * 122)

for h in HORIZONS:

    s = x[
        f"future_elapsed_ms_h{h}"
    ].dropna()

    print()
    print(
        f"HORIZON {h}"
    )

    print(
        s.describe(
            percentiles=[
                .50,
                .75,
                .90,
                .95,
                .99
            ]
        ).to_string()
    )


# =====================================================================
# SAMPLE
# =====================================================================

print()
print("=" * 122)
print("CANONICAL SAMPLE STRUCTURE")
print("=" * 122)

print()
print(
    x["flow_side"]
    .value_counts()
    .to_string()
)

print()
print(
    x["liquidity_response"]
    .value_counts()
    .to_string()
)


# =====================================================================
# GROUP SUMMARY
# =====================================================================

summary_rows = []

for side in [
    "POOLED",
    "BUY",
    "SELL"
]:

    if side == "POOLED":
        d = x
    else:
        d = x[
            x["flow_side"] == side
        ]

    for response in [
        "DEPLETION",
        "REPLENISHMENT",
        "NEUTRAL"
    ]:

        g = d[
            d["liquidity_response"] == response
        ]

        if len(g) == 0:
            continue

        row = {
            "flow_side":
                side,

            "liquidity_response":
                response,

            "n":
                len(g),

            "median_flow_magnitude":
                g["flow_magnitude"].median(),

            "median_opposing_depth":
                g["opposing_depth_t0"].median(),

            "mean_flow_purity":
                g["flow_purity"].mean(),

            "same_interval_mean_bps":
                g[
                    "directional_same_interval_bps"
                ].mean(),

            "same_interval_positive_rate":
                (
                    g[
                        "directional_same_interval_bps"
                    ] > 0
                ).mean()
        }

        for h in HORIZONS:

            col = (
                f"future_directional_bps_h{h}"
            )

            v = g[col].dropna()

            row[
                f"h{h}_n"
            ] = len(v)

            row[
                f"h{h}_mean_bps"
            ] = v.mean()

            row[
                f"h{h}_median_bps"
            ] = v.median()

            row[
                f"h{h}_positive_rate"
            ] = (
                v > 0
            ).mean()

            row[
                f"h{h}_nonzero_rate"
            ] = (
                v != 0
            ).mean()

            nz = v[
                v != 0
            ]

            row[
                f"h{h}_mean_given_move_bps"
            ] = (
                nz.mean()
                if len(nz)
                else np.nan
            )

        summary_rows.append(row)


summary = pd.DataFrame(
    summary_rows
)


# =====================================================================
# PRIMARY TABLE
# =====================================================================

print()
print("=" * 122)
print("CANONICAL PRIMARY RESPONSE COMPARISON")
print("Positive bps = midpoint moved WITH aggressive-flow direction")
print("=" * 122)

for side in [
    "POOLED",
    "BUY",
    "SELL"
]:

    print()
    print("-" * 122)
    print(side)
    print("-" * 122)

    s = summary[
        summary["flow_side"] == side
    ]

    cols = [
        "liquidity_response",
        "n",
        "median_flow_magnitude",
        "median_opposing_depth",
        "same_interval_mean_bps",
        "h1_mean_bps",
        "h1_nonzero_rate",
        "h3_mean_bps",
        "h3_nonzero_rate",
        "h5_mean_bps",
        "h5_nonzero_rate",
        "h10_mean_bps",
        "h10_nonzero_rate"
    ]

    print(
        s[cols]
        .to_string(index=False)
    )


# =====================================================================
# RAW DIFFERENCES
# =====================================================================

print()
print("=" * 122)
print("CANONICAL RAW DEPLETION MINUS REPLENISHMENT")
print("=" * 122)

for side in [
    "POOLED",
    "BUY",
    "SELL"
]:

    if side == "POOLED":
        d = x
    else:
        d = x[
            x["flow_side"] == side
        ]

    dep = d[
        d["liquidity_response"]
        ==
        "DEPLETION"
    ]

    rep = d[
        d["liquidity_response"]
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

        dv = dep[col].dropna()
        rv = rep[col].dropna()

        print(
            f"h={h:2d}  "
            f"mean diff={dv.mean() - rv.mean(): .6f} bps  "
            f"median diff={dv.median() - rv.median(): .6f} bps  "
            f"move-rate diff={(dv != 0).mean() - (rv != 0).mean(): .6f}"
        )


# =====================================================================
# FLOW MAGNITUDE + STARTING DEPTH CONTROL
# =====================================================================

print()
print("=" * 122)
print("CANONICAL STRATIFIED FLOW / DEPTH CONTROL")
print("=" * 122)

comp = x[
    x["liquidity_response"].isin(
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
        g["flow_magnitude"]
        .rank(method="first"),
        q=5,
        labels=False
    )

    g["depth_bin"] = pd.qcut(
        g["opposing_depth_t0"]
        .rank(method="first"),
        q=5,
        labels=False
    )

    parts.append(g)


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
            g["liquidity_response"]
            ==
            "DEPLETION"
        ][col].dropna()

        rep = g[
            g["liquidity_response"]
            ==
            "REPLENISHMENT"
        ][col].dropna()

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
                weight,
                len(dep),
                len(rep)
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
        f"weighted dep-rep={np.average(diffs, weights=weights): .6f} bps  "
        f"median cell diff={np.median(diffs): .6f} bps  "
        f"positive-cell-rate={(diffs > 0).mean():.4f}"
    )


# =====================================================================
# ONE-SIDED AGGRESSION ROBUSTNESS
# =====================================================================

pure = x[
    (
        (x["aggressive_buy_qty"] > 0)
        &
        (x["aggressive_sell_qty"] == 0)
    )
    |
    (
        (x["aggressive_sell_qty"] > 0)
        &
        (x["aggressive_buy_qty"] == 0)
    )
].copy()


print()
print("=" * 122)
print("CANONICAL ROBUSTNESS - ONE-SIDED AGGRESSION")
print("=" * 122)

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
            pure["flow_side"] == side
        ]

    dep = d[
        d["liquidity_response"]
        ==
        "DEPLETION"
    ]

    rep = d[
        d["liquidity_response"]
        ==
        "REPLENISHMENT"
    ]

    print()
    print(side)

    for h in HORIZONS:

        col = (
            f"future_directional_bps_h{h}"
        )

        dv = dep[col].dropna()
        rv = rep[col].dropna()

        if (
            len(dv) == 0
            or
            len(rv) == 0
        ):
            continue

        print(
            f"h={h:2d}  "
            f"dep={dv.mean(): .6f}  "
            f"rep={rv.mean(): .6f}  "
            f"diff={dv.mean() - rv.mean(): .6f} bps"
        )


# =====================================================================
# SAVE
# =====================================================================

x.to_csv(
    OUTFILE,
    index=False
)

summary.to_csv(
    SUMMARY_OUT,
    index=False
)

print()
print("SAVED ROW DATA:")
print(OUTFILE)

print()
print("SAVED SUMMARY:")
print(SUMMARY_OUT)

print()
print("=" * 122)
print("EXP-01C COMPLETE")
print("=" * 122)
