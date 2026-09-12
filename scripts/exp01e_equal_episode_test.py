import pandas as pd
import numpy as np
from pathlib import Path

INFILE = Path(
    r"C:\Users\USER\Documents\exp01c_canonical_rows.csv"
)

OUTFILE = Path(
    r"C:\Users\USER\Documents\exp01e_equal_episode_effects.csv"
)

SUMMARY_OUT = Path(
    r"C:\Users\USER\Documents\exp01e_equal_episode_summary.csv"
)

print("=" * 120)
print("EXP-01E - EQUAL-WEIGHT EPISODE TEST")
print("ONE EPISODE = ONE VOTE")
print("=" * 120)

df = pd.read_csv(INFILE)

x = df[
    df["liquidity_response"].isin(
        ["DEPLETION", "REPLENISHMENT"]
    )
].copy()

HORIZONS = [1, 3, 5, 10]

print()
print("ROWS:", f"{len(x):,}")
print(
    "TOTAL EPISODES:",
    f"{x['episode_id'].nunique():,}"
)


# =====================================================================
# BUILD WITHIN-EPISODE EFFECTS
# =====================================================================

episode_rows = []

for h in HORIZONS:

    col = f"future_directional_bps_h{h}"

    for ep, g in x.groupby("episode_id"):

        dep = g[
            g["liquidity_response"] == "DEPLETION"
        ][col].dropna()

        rep = g[
            g["liquidity_response"] == "REPLENISHMENT"
        ][col].dropna()

        if (
            len(dep) == 0
            or
            len(rep) == 0
        ):
            continue

        effect = (
            dep.mean()
            -
            rep.mean()
        )

        episode_rows.append({
            "horizon":
                h,

            "episode_id":
                int(ep),

            "effect_bps":
                effect,

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
    OUTFILE,
    index=False
)


# =====================================================================
# EQUAL-WEIGHT SUMMARY
# =====================================================================

print()
print("=" * 120)
print("EQUAL-WEIGHT EPISODE EFFECTS")
print("=" * 120)

RNG = np.random.default_rng(
    20260911
)

N_BOOT = 20000
N_SIGNFLIP = 20000

summary_rows = []


for h in HORIZONS:

    e = effects[
        effects["horizon"] == h
    ]["effect_bps"].to_numpy(
        dtype=float
    )

    n = len(e)

    nonzero = e[
        e != 0
    ]

    observed_mean = np.mean(e)
    observed_median = np.median(e)

    positive_rate_all = np.mean(
        e > 0
    )

    negative_rate_all = np.mean(
        e < 0
    )

    zero_rate = np.mean(
        e == 0
    )

    if len(nonzero):

        positive_rate_nonzero = np.mean(
            nonzero > 0
        )

        negative_rate_nonzero = np.mean(
            nonzero < 0
        )

    else:

        positive_rate_nonzero = np.nan
        negative_rate_nonzero = np.nan


    # -------------------------------------------------------------
    # EQUAL-WEIGHT EPISODE BOOTSTRAP
    #
    # Every sampled item is one episode effect.
    # -------------------------------------------------------------

    boot_means = np.empty(
        N_BOOT,
        dtype=float
    )

    for b in range(N_BOOT):

        sample = RNG.choice(
            e,
            size=n,
            replace=True
        )

        boot_means[b] = np.mean(
            sample
        )


    ci_low = np.quantile(
        boot_means,
        0.025
    )

    ci_high = np.quantile(
        boot_means,
        0.975
    )

    boot_p_positive = np.mean(
        boot_means > 0
    )


    # -------------------------------------------------------------
    # SIGN-FLIP RANDOMIZATION TEST
    #
    # Null:
    # Episode effect is centered at zero.
    #
    # Preserve absolute magnitude but randomly reverse episode sign.
    # -------------------------------------------------------------

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
            abs_e * signs
        )


    # One-sided test because frozen proposition is:
    # depletion > replenishment

    randomization_p = (
        1
        +
        np.sum(
            null_means
            >=
            observed_mean
        )
    ) / (
        N_SIGNFLIP + 1
    )


    print()
    print("-" * 120)

    print(
        f"HORIZON {h}"
    )

    print("-" * 120)

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
            randomization_p
    })


# =====================================================================
# EFFECT CONCENTRATION
# =====================================================================

print()
print("=" * 120)
print("EFFECT CONCENTRATION AUDIT")
print("=" * 120)


for h in HORIZONS:

    e = effects[
        effects["horizon"] == h
    ].copy()

    e["abs_effect"] = np.abs(
        e["effect_bps"]
    )

    e = e.sort_values(
        "abs_effect",
        ascending=False
    )

    total_abs = e[
        "abs_effect"
    ].sum()

    print()
    print(
        f"H{h}"
    )

    for frac in [
        0.05,
        0.10,
        0.20
    ]:

        k = max(
            1,
            int(
                np.ceil(
                    len(e) * frac
                )
            )
        )

        share = (
            e.head(k)[
                "abs_effect"
            ].sum()
            /
            total_abs
            if total_abs > 0
            else np.nan
        )

        print(
            f"Top {int(frac * 100):2d}% episodes "
            f"share of absolute effect magnitude: "
            f"{share:.6f}"
        )


summary = pd.DataFrame(
    summary_rows
)

summary.to_csv(
    SUMMARY_OUT,
    index=False
)


print()
print("SAVED EPISODE EFFECTS:")
print(OUTFILE)

print()
print("SAVED SUMMARY:")
print(SUMMARY_OUT)

print()
print("=" * 120)
print("EXP-01E COMPLETE")
print("=" * 120)
