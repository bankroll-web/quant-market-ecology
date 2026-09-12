import json
import os
import tempfile
import gc
import time
from pathlib import Path
from datetime import datetime, timezone

import pandas as pd
import pyarrow.parquet as pq
import pyarrow.compute as pc

try:
    import zstandard as zstd
except ImportError:
    zstd = None


# =====================================================================
# PATHS
# =====================================================================

ROOT = Path(r"C:\Users\USER\Documents")

ORDERBOOK_ROOT = (
    ROOT
    / "Audit_V2_1"
    / "Raw_Orderbooks"
)

TRADES_ROOT = (
    ROOT
    / "CryptoHFT_Trades_8Hours"
)

SPEC_PATH = (
    ROOT
    / "EXP01_FROZEN_REPLICATION_SPEC.json"
)

OUT_CSV = (
    ROOT
    / "exp01_replication_gate0_inventory.csv"
)


# =====================================================================
# FROZEN REPLICATION DESIGN
# =====================================================================

DISCOVERY_HOUR = "2026-05-25_00"

REPLICATION_HOURS = [
    "2026-05-25_04",
    "2026-05-25_12",
    "2026-05-25_18",
    "2026-05-26_15",
    "2026-05-26_21",
]

FROZEN_SPEC = {

    "experiment":
        "EXP-01 Absorption vs Yielding",

    "stage":
        "Independent replication",

    "discovery_hour":
        DISCOVERY_HOUR,

    "replication_hours":
        REPLICATION_HOURS,

    "market":
        "Binance Futures BTCUSDT",

    "flow_definition": {
        "buy":
            "signed aggressive flow > 0",

        "sell":
            "signed aggressive flow < 0",

        "buyer_maker_true":
            "seller aggressive",

        "buyer_maker_false":
            "buyer aggressive"
    },

    "liquidity_region":
        "0-5 ticks from PRE-event opposing touch",

    "response_definition": {
        "replenishment":
            "opposing near-touch net displayed liquidity > 0",

        "depletion":
            "opposing near-touch net displayed liquidity < 0",

        "neutral":
            "opposing near-touch net displayed liquidity == 0"
    },

    "anchor_timestamp_rule":
        "exclude starting intervals with trades exactly at t1",

    "future_state_rule":
        "future midpoint measured using literal consecutive valid L2 events within same verified episode",

    "primary_horizons_events": [
        3,
        5,
        10
    ],

    "diagnostic_horizon_events": [
        1
    ],

    "discovery_result": {
        "H1":
            "failed equal-episode robustness",

        "H3":
            "survived equal-episode robustness",

        "H5":
            "survived equal-episode robustness",

        "H10":
            "survived equal-episode robustness"
    },

    "primary_proposition":
        "future directional displacement under depletion exceeds replenishment",

    "direction_policy":
        "retain pooled, BUY and SELL; no post-hoc side selection",

    "controls": [
        "aggressive flow magnitude",
        "starting opposing 5-level depth"
    ],

    "replication_rules": [
        "no change to 0-5 tick region",
        "no optimization of H3/H5/H10",
        "no new flow threshold",
        "no selecting only favorable BUY or SELL side",
        "no discarding valid unfavorable hours",
        "data quality must be evaluated independently of hypothesis outcome"
    ]
}


# =====================================================================
# WRITE SPEC ONLY IF IT DOES NOT ALREADY EXIST
# =====================================================================

if SPEC_PATH.exists():

    print("=" * 120)
    print("FROZEN SPEC ALREADY EXISTS")
    print("=" * 120)

    print(SPEC_PATH)

else:

    with open(
        SPEC_PATH,
        "w",
        encoding="utf-8"
    ) as f:

        json.dump(
            FROZEN_SPEC,
            f,
            indent=2
        )

    print("=" * 120)
    print("FROZEN REPLICATION SPEC CREATED")
    print("=" * 120)

    print(SPEC_PATH)


# =====================================================================
# FILE DISCOVERY
# =====================================================================

def find_hour_file(root, hour_token):

    candidates = []

    if not root.exists():
        return None, []

    for p in root.rglob("*"):

        if not p.is_file():
            continue

        name = p.name.lower()

        if hour_token.lower() in name:
            candidates.append(p)

    candidates = sorted(candidates)

    if len(candidates) == 1:
        return candidates[0], candidates

    # Prefer parquet-ish names if multiple.
    parquet_like = [
        p for p in candidates
        if ".parquet" in p.name.lower()
    ]

    if len(parquet_like) == 1:
        return parquet_like[0], candidates

    if parquet_like:
        return parquet_like[0], candidates

    if candidates:
        return candidates[0], candidates

    return None, []


# =====================================================================
# PARQUET / OUTER-ZSTD HANDLING
# =====================================================================

ZSTD_MAGIC = bytes.fromhex(
    "28 B5 2F FD"
)

PARQUET_MAGIC = b"PAR1"


def read_magic(path, n=4):

    with open(path, "rb") as f:
        return f.read(n)


def prepare_parquet(path):

    """
    Returns:
      parquet_path
      temporary_path_or_None
      outer_format
    """

    magic = read_magic(
        path,
        4
    )

    if magic == PARQUET_MAGIC:

        return (
            path,
            None,
            "PARQUET"
        )

    if magic == ZSTD_MAGIC:

        if zstd is None:
            raise RuntimeError(
                "Outer Zstandard file detected but "
                "Python package 'zstandard' is not installed."
            )

        fd, tmp_name = tempfile.mkstemp(
            suffix=".parquet"
        )

        os.close(fd)

        tmp_path = Path(
            tmp_name
        )

        dctx = zstd.ZstdDecompressor()

        with open(path, "rb") as src, \
             open(tmp_path, "wb") as dst:

            dctx.copy_stream(
                src,
                dst
            )

        inner_magic = read_magic(
            tmp_path,
            4
        )

        if inner_magic != PARQUET_MAGIC:

            tmp_path.unlink(
                missing_ok=True
            )

            raise RuntimeError(
                "Outer Zstandard decompressed successfully "
                "but inner file is not PAR1 parquet."
            )

        return (
            tmp_path,
            tmp_path,
            "OUTER_ZSTD_PARQUET"
        )

    raise RuntimeError(
        "Unknown file signature: "
        + magic.hex()
    )


# =====================================================================
# TIMESTAMP AUDIT
# =====================================================================

def numeric_timestamp_summary(
    parquet_path,
    candidate_columns
):

    schema = pq.read_schema(
        parquet_path
    )

    names = set(
        schema.names
    )

    chosen = None

    for c in candidate_columns:

        if c in names:
            chosen = c
            break

    if chosen is None:

        return {
            "timestamp_column": None,
            "timestamp_min_raw": None,
            "timestamp_max_raw": None
        }

    table = pq.read_table(
        parquet_path,
        columns=[chosen]
    )

    arr = table[
        chosen
    ]

    result = pc.min_max(
        arr
    ).as_py()

    return {
        "timestamp_column":
            chosen,

        "timestamp_min_raw":
            result.get("min"),

        "timestamp_max_raw":
            result.get("max")
    }


# =====================================================================
# FILE AUDIT
# =====================================================================

def audit_file(
    path,
    dataset_type
):

    out = {
        "found":
            False,

        "path":
            None,

        "size_mb":
            None,

        "outer_format":
            None,

        "rows":
            None,

        "columns":
            None,

        "column_count":
            None,

        "timestamp_column":
            None,

        "timestamp_min_raw":
            None,

        "timestamp_max_raw":
            None,

        "schema_pass":
            False,

        "error":
            None
    }

    if path is None:
        out["error"] = "FILE_NOT_FOUND"
        return out

    out["found"] = True

    out["path"] = str(
        path
    )

    out["size_mb"] = (
        path.stat().st_size
        /
        1024
        /
        1024
    )

    tmp = None

    try:

        parquet_path, tmp, outer = (
            prepare_parquet(
                path
            )
        )

        out[
            "outer_format"
        ] = outer

        pf = pq.ParquetFile(
            parquet_path
        )

        schema = pf.schema_arrow

        columns = schema.names

        out["rows"] = (
            pf.metadata.num_rows
        )

        out["columns"] = (
            ",".join(columns)
        )

        out["column_count"] = (
            len(columns)
        )


        if dataset_type == "ORDERBOOK":

            required = {
                "received_time",
                "event_time",
                "symbol",
                "event_type",
                "side",
                "price",
                "quantity"
            }

            sequence_any = (
                "final_update_id" in columns
                or
                "last_update_id" in columns
            )

            out["schema_pass"] = (
                required.issubset(
                    set(columns)
                )
                and
                sequence_any
            )

            ts = numeric_timestamp_summary(
                parquet_path,
                [
                    "event_time",
                    "received_time",
                    "transaction_time"
                ]
            )


        else:

            required = {
                "received_time",
                "event_time",
                "symbol",
                "price",
                "quantity",
                "is_buyer_maker"
            }

            out["schema_pass"] = (
                required.issubset(
                    set(columns)
                )
            )

            ts = numeric_timestamp_summary(
                parquet_path,
                [
                    "trade_time",
                    "event_time",
                    "received_time"
                ]
            )


        out.update(
            ts
        )

    except Exception as exc:

        out["error"] = (
            type(exc).__name__
            + ": "
            + str(exc)
        )

    finally:

        # Windows-safe cleanup:
        # pyarrow can retain an open handle to temporary parquet files.
        if "pf" in locals():

            try:
                pf.close()
            except Exception:
                pass

            try:
                del pf
            except Exception:
                pass

        gc.collect()

        if tmp is not None:

            deleted = False

            for attempt in range(10):

                try:

                    tmp.unlink(
                        missing_ok=True
                    )

                    deleted = True
                    break

                except PermissionError:

                    gc.collect()
                    time.sleep(0.25)

            if not deleted:

                print(
                    "  WARNING: temporary parquet still locked; "
                    "leaving it for later cleanup:",
                    tmp
                )

    return out


# =====================================================================
# RUN GATE 0
# =====================================================================

print()
print("=" * 120)
print("EXP-01 REPLICATION - GATE 0")
print("RAW FILE / PARQUET / SCHEMA INTEGRITY")
print("=" * 120)

rows = []


for hour in REPLICATION_HOURS:

    print()
    print("-" * 120)
    print(hour)
    print("-" * 120)

    ob_file, ob_candidates = (
        find_hour_file(
            ORDERBOOK_ROOT,
            hour
        )
    )

    tr_file, tr_candidates = (
        find_hour_file(
            TRADES_ROOT,
            hour
        )
    )

    ob = audit_file(
        ob_file,
        "ORDERBOOK"
    )

    tr = audit_file(
        tr_file,
        "TRADES"
    )


    gate0_pass = bool(
        ob["found"]
        and
        tr["found"]
        and
        ob["schema_pass"]
        and
        tr["schema_pass"]
        and
        ob["rows"]
        and
        tr["rows"]
    )


    print(
        "ORDERBOOK:"
    )

    print(
        "  file:",
        ob["path"]
    )

    print(
        "  size MB:",
        ob["size_mb"]
    )

    print(
        "  format:",
        ob["outer_format"]
    )

    print(
        "  rows:",
        ob["rows"]
    )

    print(
        "  columns:",
        ob["column_count"]
    )

    print(
        "  timestamp:",
        ob["timestamp_column"]
    )

    print(
        "  schema pass:",
        ob["schema_pass"]
    )

    if ob["error"]:
        print(
            "  ERROR:",
            ob["error"]
        )


    print()
    print(
        "TRADES:"
    )

    print(
        "  file:",
        tr["path"]
    )

    print(
        "  size MB:",
        tr["size_mb"]
    )

    print(
        "  format:",
        tr["outer_format"]
    )

    print(
        "  rows:",
        tr["rows"]
    )

    print(
        "  columns:",
        tr["column_count"]
    )

    print(
        "  timestamp:",
        tr["timestamp_column"]
    )

    print(
        "  schema pass:",
        tr["schema_pass"]
    )

    if tr["error"]:
        print(
            "  ERROR:",
            tr["error"]
        )


    print()
    print(
        "GATE 0:",
        "PASS"
        if gate0_pass
        else
        "FAIL"
    )


    rows.append({

        "hour":
            hour,

        "orderbook_found":
            ob["found"],

        "orderbook_path":
            ob["path"],

        "orderbook_size_mb":
            ob["size_mb"],

        "orderbook_format":
            ob["outer_format"],

        "orderbook_rows":
            ob["rows"],

        "orderbook_column_count":
            ob["column_count"],

        "orderbook_schema_pass":
            ob["schema_pass"],

        "orderbook_timestamp_column":
            ob["timestamp_column"],

        "orderbook_timestamp_min_raw":
            ob["timestamp_min_raw"],

        "orderbook_timestamp_max_raw":
            ob["timestamp_max_raw"],

        "orderbook_error":
            ob["error"],


        "trades_found":
            tr["found"],

        "trades_path":
            tr["path"],

        "trades_size_mb":
            tr["size_mb"],

        "trades_format":
            tr["outer_format"],

        "trades_rows":
            tr["rows"],

        "trades_column_count":
            tr["column_count"],

        "trades_schema_pass":
            tr["schema_pass"],

        "trades_timestamp_column":
            tr["timestamp_column"],

        "trades_timestamp_min_raw":
            tr["timestamp_min_raw"],

        "trades_timestamp_max_raw":
            tr["timestamp_max_raw"],

        "trades_error":
            tr["error"],

        "gate0_pass":
            gate0_pass
    })


result = pd.DataFrame(
    rows
)

result.to_csv(
    OUT_CSV,
    index=False
)


# =====================================================================
# FINAL TABLE
# =====================================================================

print()
print("=" * 120)
print("GATE 0 SUMMARY")
print("=" * 120)

cols = [
    "hour",
    "orderbook_rows",
    "trades_rows",
    "orderbook_schema_pass",
    "trades_schema_pass",
    "gate0_pass"
]

print(
    result[
        cols
    ].to_string(
        index=False
    )
)

print()
print(
    "PASS HOURS:",
    int(
        result[
            "gate0_pass"
        ].sum()
    ),
    "/",
    len(result)
)

print()
print(
    "FROZEN SPEC:"
)

print(
    SPEC_PATH
)

print()
print(
    "GATE 0 OUTPUT:"
)

print(
    OUT_CSV
)

print()
print("=" * 120)
print("GATE 0 COMPLETE")
print("=" * 120)
