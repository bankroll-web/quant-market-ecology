from pathlib import Path
import json
import pandas as pd

ROOT = Path(r"C:\Users\USER\Documents")

SPEC_FILE = ROOT / "DBR_FROZEN_SPEC_20260910.json"

SOURCE_CANDIDATES = [
    ROOT / "experiment24_stop_cluster_ecology_BTCUSD.csv",
    ROOT / "experiment18_market_ecology_state_BTCUSD.csv",
]

OUT_STATUS = ROOT / "DBR_PROSPECTIVE_STATUS.csv"
OUT_REPORT = ROOT / "DBR_PROSPECTIVE_STATUS.txt"

with open(SPEC_FILE, "r", encoding="utf-8-sig") as f:
    spec = json.load(f)

cutoff = pd.Timestamp(
    spec["discovery_cutoff_utc"]
)

src = None

for candidate in SOURCE_CANDIDATES:
    if candidate.exists():
        test = pd.read_csv(
            candidate,
            nrows=2
        )

        needed = {
            "datetime_utc",
            "btc_return_20m_bps",
            "position_reallocation",
            "long_cluster_changed",
            "long_cluster_migration_bps",
            "short_cluster_changed",
            "short_cluster_migration_bps",
        }

        if needed.issubset(
            set(test.columns)
        ):
            src = candidate
            break

if src is None:
    raise RuntimeError(
        "Could not find a current ecology file containing the DBR fields."
    )

df = pd.read_csv(src)

df["datetime_utc"] = pd.to_datetime(
    df["datetime_utc"],
    utc=True,
    errors="coerce"
)

df = (
    df.dropna(subset=["datetime_utc"])
      .sort_values("datetime_utc")
      .reset_index(drop=True)
)

numeric = [
    "btc_return_20m_bps",
    "position_reallocation",
    "long_cluster_migration_bps",
    "short_cluster_migration_bps",
]

for c in numeric:
    df[c] = pd.to_numeric(
        df[c],
        errors="coerce"
    )

def bool_clean(x):

    if pd.isna(x):
        return pd.NA

    if isinstance(x, bool):
        return x

    s = str(x).strip().lower()

    if s in ["true", "1"]:
        return True

    if s in ["false", "0"]:
        return False

    return pd.NA

for c in [
    "long_cluster_changed",
    "short_cluster_changed",
]:
    df[c] = (
        df[c]
        .map(bool_clean)
        .astype("boolean")
    )

historical = df[
    df["datetime_utc"] <= cutoff
].copy()

prospective = df[
    df["datetime_utc"] > cutoff
].copy()

# ------------------------------------------------------------
# Future response.
#
# This monitor assumes the source remains on the genuine
# 20-minute ecology clock.
# ------------------------------------------------------------

prospective["next_time"] = (
    prospective["datetime_utc"]
    .shift(-1)
)

prospective["next_reallocation"] = (
    prospective["position_reallocation"]
    .shift(-1)
)

prospective["next_gap_minutes"] = (
    (
        prospective["next_time"]
        -
        prospective["datetime_utc"]
    )
    .dt.total_seconds()
    / 60.0
)

prospective["valid_next20"] = (
    prospective["next_gap_minutes"]
    .between(19, 21)
)

prospective["event_type"] = pd.Series(
    "NONE",
    index=prospective.index,
    dtype="string"
)

for i in prospective.index:

    btc = prospective.at[
        i,
        "btc_return_20m_bps"
    ]

    if pd.isna(btc):
        continue

    lc = prospective.at[
        i,
        "long_cluster_changed"
    ]

    sc = prospective.at[
        i,
        "short_cluster_changed"
    ]

    lm = prospective.at[
        i,
        "long_cluster_migration_bps"
    ]

    sm = prospective.at[
        i,
        "short_cluster_migration_bps"
    ]

    lc_bool = (
        False
        if pd.isna(lc)
        else bool(lc)
    )

    sc_bool = (
        False
        if pd.isna(sc)
        else bool(sc)
    )

    if btc < 0:

        if (
            lc_bool
            and pd.notna(lm)
            and lm < 0
        ):
            prospective.at[
                i,
                "event_type"
            ] = "DOWN_DBR"

        elif not lc_bool:
            prospective.at[
                i,
                "event_type"
            ] = "DOWN_ANCHORED_CONTROL"

        else:
            prospective.at[
                i,
                "event_type"
            ] = "DOWN_OTHER"

    elif btc > 0:

        if (
            sc_bool
            and pd.notna(sm)
            and sm > 0
        ):
            prospective.at[
                i,
                "event_type"
            ] = "UP_DBR"

        elif not sc_bool:
            prospective.at[
                i,
                "event_type"
            ] = "UP_ANCHORED_CONTROL"

        else:
            prospective.at[
                i,
                "event_type"
            ] = "UP_OTHER"

prospective["counter_response_20m"] = pd.NA

down_mask = (
    prospective["event_type"]
    .isin([
        "DOWN_DBR",
        "DOWN_ANCHORED_CONTROL",
    ])
    &
    prospective["valid_next20"]
)

up_mask = (
    prospective["event_type"]
    .isin([
        "UP_DBR",
        "UP_ANCHORED_CONTROL",
    ])
    &
    prospective["valid_next20"]
)

prospective.loc[
    down_mask,
    "counter_response_20m"
] = prospective.loc[
    down_mask,
    "next_reallocation"
]

prospective.loc[
    up_mask,
    "counter_response_20m"
] = -prospective.loc[
    up_mask,
    "next_reallocation"
]

prospective[
    "counter_response_20m"
] = pd.to_numeric(
    prospective[
        "counter_response_20m"
    ],
    errors="coerce"
)

prospective.to_csv(
    OUT_STATUS,
    index=False
)

counts = (
    prospective[
        "event_type"
    ]
    .value_counts()
)

down_dbr = int(
    counts.get(
        "DOWN_DBR",
        0
    )
)

up_dbr = int(
    counts.get(
        "UP_DBR",
        0
    )
)

down_control = int(
    counts.get(
        "DOWN_ANCHORED_CONTROL",
        0
    )
)

up_control = int(
    counts.get(
        "UP_ANCHORED_CONTROL",
        0
    )
)

lines = []

lines.append(
    "=" * 100
)

lines.append(
    "DBR PROSPECTIVE REPLICATION STATUS"
)

lines.append(
    "=" * 100
)

lines.append("")

lines.append(
    f"Frozen specification : {SPEC_FILE.name}"
)

lines.append(
    f"Source               : {src}"
)

lines.append(
    f"Discovery cutoff     : {cutoff}"
)

lines.append(
    "Eligibility rule     : datetime_utc STRICTLY GREATER than discovery cutoff"
)

lines.append("")

lines.append(
    f"Historical rows excluded : {len(historical):,}"
)

lines.append(
    f"Prospective rows         : {len(prospective):,}"
)

if len(prospective):

    lines.append(
        f"Prospective first        : {prospective['datetime_utc'].min()}"
    )

    lines.append(
        f"Prospective latest       : {prospective['datetime_utc'].max()}"
    )

else:

    lines.append(
        "Prospective first        : NONE YET"
    )

    lines.append(
        "Prospective latest       : NONE YET"
    )

lines.append("")

lines.append(
    f"DOWN_DBR              : {down_dbr}"
)

lines.append(
    f"DOWN_ANCHORED_CONTROL : {down_control}"
)

lines.append(
    f"UP_DBR                : {up_dbr}"
)

lines.append(
    f"UP_ANCHORED_CONTROL   : {up_control}"
)

lines.append("")

lines.append(
    "PRIMARY HORIZON: 20 minutes"
)

lines.append(
    "PRIMARY QUESTION: Does prospective DBR show stronger counter-directional reallocation than its anchored control?"
)

lines.append("")

lines.append(
    "IMPORTANT:"
)

lines.append(
    "- Old discovery rows are excluded."
)

lines.append(
    "- DBR definition is frozen."
)

lines.append(
    "- No threshold optimization."
)

lines.append(
    "- No rule changes after seeing prospective outcomes."
)

lines.append(
    "- Small event counts mean WAIT, not modify the hypothesis."
)

lines.append(
    "- This is research monitoring only."
)

OUT_REPORT.write_text(
    "\n".join(lines),
    encoding="utf-8"
)

print(
    "\n".join(lines)
)

print()
print(
    f"Status CSV : {OUT_STATUS}"
)
print(
    f"Status TXT : {OUT_REPORT}"
)
print()
print(
    "DBR MONITOR COMPLETE"
)
