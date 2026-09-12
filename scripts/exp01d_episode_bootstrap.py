import pandas as pd
import numpy as np
from pathlib import Path

INFILE = Path(
    r"C:\Users\USER\Documents\exp01c_canonical_rows.csv"
)

OUTFILE = Path(
    r"C:\Users\USER\Documents\exp01d_episode_bootstrap.csv"
)

print("=" * 118)
print("EXP-01D - EPISODE-LEVEL BOOTSTRAP")
print("=" * 118)

df = pd.read_csv(INFILE)

HORIZONS = [1, 3, 5, 10]

# Only the two states being compared.
x = df[
    df["liquidity_response"].isin(
        ["DEPLETION", "REPLENISHMENT"]
    )
].copy()

print()
print("ROWS:", f"{len(x):,}")
print(
    "EPISODES:",
    f"{x['episode_id'].nunique():,}"
)

print()
print(
    x["liquidity_response"]
    .value_counts()
    .to_string()
)


# =====================================================================
# OBSERVED DIFFERENCE
# =====================================================================

observed = {}

print()
print("=" * 118)
print("OBSERVED DEPLETION - REPLENISHMENT")
print("=" * 118)

for h in HORIZONS:

    col = f"future_directional_bps_h{h}"

    dep = x[
        x["liquidity_response"] == "DEPLETION"
    ][col].dropna()

    rep = x[
        x["liquidity_response"] == "REPLENISHMENT"
    ][col].dropna()

    diff = (
        dep.mean()
        -
        rep.mean()
    )

    observed[h] = diff

    print(
        f"H{h}: {diff: .6f} bps"
    )


# =====================================================================
# EPISODE INVENTORY
# =====================================================================

episode_ids = np.array(
    sorted(
        x["episode_id"].unique()
    )
)

episode_frames = {
    ep: x[
        x["episode_id"] == ep
    ].copy()
    for ep in episode_ids
}

N_EPISODES = len(
    episode_ids
)

print()
print(
    "BOOTSTRAP UNIT = FULL EPISODE"
)

print(
    "N EPISODES =",
    N_EPISODES
)


# =====================================================================
# CLUSTER BOOTSTRAP
# =====================================================================

RNG = np.random.default_rng(
    20260911
)

N_BOOT = 10000

boot = {
    h: []
    for h in HORIZONS
}


for b in range(N_BOOT):

    sampled_ids = RNG.choice(
        episode_ids,
        size=N_EPISODES,
        replace=True
    )

    # Important:
    # duplicated episodes remain duplicated in bootstrap sample.
    pieces = [
        episode_frames[ep]
        for ep in sampled_ids
    ]

    sample = pd.concat(
        pieces,
        ignore_index=True
    )

    for h in HORIZONS:

        col = (
            f"future_directional_bps_h{h}"
        )

        dep = sample[
            sample["liquidity_response"]
            ==
            "DEPLETION"
        ][col].dropna()

        rep = sample[
            sample["liquidity_response"]
            ==
            "REPLENISHMENT"
        ][col].dropna()

        if (
            len(dep) == 0
            or
            len(rep) == 0
        ):
            continue

        boot[h].append(
            dep.mean()
            -
            rep.mean()
        )


# =====================================================================
# SUMMARY
# =====================================================================

rows = []

print()
print("=" * 118)
print("EPISODE-BOOTSTRAP RESULTS")
print("=" * 118)


for h in HORIZONS:

    arr = np.asarray(
        boot[h],
        dtype=float
    )

    low = np.quantile(
        arr,
        0.025
    )

    high = np.quantile(
        arr,
        0.975
    )

    median = np.median(
        arr
    )

    mean = np.mean(
        arr
    )

    p_positive = np.mean(
        arr > 0
    )

    p_nonpositive = np.mean(
        arr <= 0
    )

    print()
    print(
        f"H{h}"
    )

    print(
        "Observed diff       :",
        f"{observed[h]: .6f} bps"
    )

    print(
        "Bootstrap mean      :",
        f"{mean: .6f} bps"
    )

    print(
        "Bootstrap median    :",
        f"{median: .6f} bps"
    )

    print(
        "95% percentile CI   :",
        f"[{low: .6f}, {high: .6f}] bps"
    )

    print(
        "P(diff > 0)         :",
        f"{p_positive:.6f}"
    )

    print(
        "P(diff <= 0)        :",
        f"{p_nonpositive:.6f}"
    )

    rows.append({
        "horizon_events":
            h,

        "observed_diff_bps":
            observed[h],

        "bootstrap_mean_bps":
            mean,

        "bootstrap_median_bps":
            median,

        "ci_2_5_bps":
            low,

        "ci_97_5_bps":
            high,

        "p_diff_positive":
            p_positive,

        "p_diff_nonpositive":
            p_nonpositive,

        "bootstrap_draws":
            len(arr)
    })


# =====================================================================
# EPISODE CONTRIBUTION AUDIT
# =====================================================================

print()
print("=" * 118)
print("EPISODE CONTRIBUTION AUDIT")
print("=" * 118)


for h in HORIZONS:

    col = (
        f"future_directional_bps_h{h}"
    )

    episode_effects = []

    for ep, g in x.groupby(
        "episode_id"
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
            len(dep) == 0
            or
            len(rep) == 0
        ):
            continue

        episode_effects.append(
            (
                int(ep),
                dep.mean()
                -
                rep.mean(),
                len(dep),
                len(rep)
            )
        )


    if not episode_effects:

        print(
            f"H{h}: no episodes containing both states"
        )
        continue


    effects = np.array(
        [
            z[1]
            for z in episode_effects
        ],
        dtype=float
    )

    print()
    print(
        f"H{h}: episodes containing BOTH states =",
        len(effects)
    )

    print(
        "Episode median effect:",
        f"{np.median(effects): .6f} bps"
    )

    print(
        "Episode positive rate :",
        f"{np.mean(effects > 0):.6f}"
    )

    print(
        "Episode effect p25/p75:",
        f"{np.quantile(effects, .25): .6f}",
        f"{np.quantile(effects, .75): .6f}"
    )


result = pd.DataFrame(
    rows
)

result.to_csv(
    OUTFILE,
    index=False
)

print()
print("SAVED:")
print(OUTFILE)

print()
print("=" * 118)
print("EXP-01D COMPLETE")
print("=" * 118)
