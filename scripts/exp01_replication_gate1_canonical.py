import pandas as pd
import pyarrow.parquet as pq
import pyarrow as pa
import zstandard as zstd
import io
from pathlib import Path


ROOT = Path(r"C:\Users\USER\Documents")

BOOK_DIR = (
    ROOT
    / "Audit_V2_1"
    / "Raw_Orderbooks"
)

OUT_DIR = (
    ROOT
    / "EXP01_REPLICATION"
)

OUT_DIR.mkdir(
    exist_ok=True
)

SUMMARY_FILE = (
    OUT_DIR
    / "gate1_canonical_summary.csv"
)


REPLICATION_HOURS = [
    "2026-05-25_04",
    "2026-05-25_12",
    "2026-05-25_18",
    "2026-05-26_15",
    "2026-05-26_21",
]


print("=" * 110)
print("EXP-01 REPLICATION - CANONICAL GATE 1")
print("EXACT D06 SNAPSHOT-BRIDGE + SEQUENCE REPLAY")
print("=" * 110)


# ======================================================================
# SAME CRYPTOHFT READER AS ORIGINAL D06
# ======================================================================

def read_cryptohft(path):

    with open(path, "rb") as f:
        first4 = f.read(4)

    if first4 == b"PAR1":

        return pd.read_parquet(
            path
        )

    if first4 == b"\x28\xb5\x2f\xfd":

        with open(path, "rb") as f:
            compressed = f.read()

        dctx = zstd.ZstdDecompressor()

        with dctx.stream_reader(
            io.BytesIO(compressed)
        ) as reader:

            raw = reader.read()

        if raw[:4] != b"PAR1":

            raise RuntimeError(
                "Inner payload is not Parquet"
            )

        return pq.read_table(
            pa.BufferReader(raw)
        ).to_pandas()

    raise RuntimeError(
        f"Unknown file signature: {first4!r}"
    )


# ======================================================================
# EXACT D06 REPLAY ENGINE
# ======================================================================

def replay_hour(hour):

    book_file = (
        BOOK_DIR
        / f"BTCUSDT_orderbook_{hour}.parquet"
    )

    if not book_file.exists():

        raise FileNotFoundError(
            str(book_file)
        )


    print()
    print("-" * 110)
    print(hour)
    print("-" * 110)

    df = read_cryptohft(
        book_file
    )

    print(
        "ROWS LOADED             :",
        f"{len(df):,}"
    )


    # ------------------------------------------------------------------
    # NUMERIC CONVERSION
    # ------------------------------------------------------------------

    df["price_num"] = pd.to_numeric(
        df["price"],
        errors="raise"
    )

    df["qty_num"] = pd.to_numeric(
        df["quantity"],
        errors="raise"
    )

    df["event_type"] = (
        df["event_type"]
        .astype(str)
        .str.lower()
    )


    # ------------------------------------------------------------------
    # BUILD LOGICAL SNAPSHOT EVENTS
    # Exact grouping from D06.
    # ------------------------------------------------------------------

    snap_rows = df[
        df["event_type"] == "snapshot"
    ].copy()

    snapshot_groups = []

    for key, g in snap_rows.groupby(
        [
            "received_time",
            "event_time",
            "last_update_id"
        ],
        sort=False,
        dropna=False
    ):

        (
            received_time,
            event_time,
            last_update_id
        ) = key

        snapshot_groups.append({

            "received_time":
                int(received_time),

            "event_time":
                int(event_time),

            "last_update_id":
                int(last_update_id),

            "rows":
                g
        })


    # ------------------------------------------------------------------
    # BUILD LOGICAL UPDATE EVENTS
    # Exact grouping from D06.
    # ------------------------------------------------------------------

    upd_rows = df[
        df["event_type"] == "update"
    ].copy()

    update_groups = []

    for key, g in upd_rows.groupby(
        [
            "received_time",
            "event_time",
            "transaction_time",
            "first_update_id",
            "final_update_id",
            "prev_final_update_id"
        ],
        sort=False,
        dropna=False
    ):

        (
            received_time,
            event_time,
            transaction_time,
            first_update_id,
            final_update_id,
            prev_final_update_id
        ) = key

        update_groups.append({

            "received_time":
                int(received_time),

            "event_time":
                int(event_time),

            "transaction_time":
                int(transaction_time),

            "U":
                int(first_update_id),

            "u":
                int(final_update_id),

            "pu":
                int(prev_final_update_id),

            "rows":
                g
        })


    print(
        "SNAPSHOT EVENTS         :",
        f"{len(snapshot_groups):,}"
    )

    print(
        "UPDATE EVENTS           :",
        f"{len(update_groups):,}"
    )


    # ------------------------------------------------------------------
    # COMBINE EVENTS
    # Exact D06 ordering.
    # ------------------------------------------------------------------

    events = []

    for s in snapshot_groups:

        events.append({
            "kind": "snapshot",
            **s
        })

    for u in update_groups:

        events.append({
            "kind": "update",
            **u
        })


    events.sort(
        key=lambda x: (
            x["received_time"],
            0 if x["kind"] == "snapshot" else 1,
            x.get(
                "u",
                x.get(
                    "last_update_id",
                    0
                )
            )
        )
    )


    # ------------------------------------------------------------------
    # LOCAL BOOK
    # ------------------------------------------------------------------

    bids = {}
    asks = {}

    book_valid = False
    waiting_for_bridge = False

    local_update_id = None
    snapshot_last_id = None

    snapshots_loaded = 0
    valid_bridges = 0
    invalid_bridges = 0
    continuous_updates = 0
    sequence_failures = 0
    stale_updates_skipped = 0

    level_inserts = 0
    level_updates = 0
    level_deletes = 0

    states = []

    current_episode_id = 0


    def apply_levels(rows):

        nonlocal level_inserts
        nonlocal level_updates
        nonlocal level_deletes

        for row in rows.itertuples(
            index=False
        ):

            side = row.side

            price = float(
                row.price_num
            )

            qty = float(
                row.qty_num
            )

            book = (
                bids
                if side == "bid"
                else asks
            )

            old_qty = book.get(
                price
            )

            if qty == 0.0:

                if price in book:

                    del book[
                        price
                    ]

                    level_deletes += 1

            else:

                if old_qty is None:

                    level_inserts += 1

                else:

                    level_updates += 1

                book[
                    price
                ] = qty


    def load_snapshot(rows):

        bids.clear()
        asks.clear()

        for row in rows.itertuples(
            index=False
        ):

            price = float(
                row.price_num
            )

            qty = float(
                row.qty_num
            )

            if qty <= 0:
                continue

            if row.side == "bid":

                bids[
                    price
                ] = qty

            elif row.side == "ask":

                asks[
                    price
                ] = qty


    def record_state(event):

        if not bids or not asks:
            return

        best_bid = max(
            bids
        )

        best_ask = min(
            asks
        )

        crossed = int(
            best_ask <= best_bid
        )

        top_bids = sorted(
            bids.items(),
            reverse=True
        )[:5]

        top_asks = sorted(
            asks.items()
        )[:5]

        bid_qty_5 = sum(
            q for _, q in top_bids
        )

        ask_qty_5 = sum(
            q for _, q in top_asks
        )

        denom = (
            bid_qty_5
            +
            ask_qty_5
        )

        if denom > 0:

            obi5 = (
                bid_qty_5
                -
                ask_qty_5
            ) / denom

        else:

            obi5 = float(
                "nan"
            )

        mid = (
            best_bid
            +
            best_ask
        ) / 2.0

        spread = (
            best_ask
            -
            best_bid
        )

        states.append({

            "hour":
                hour,

            "episode_id":
                current_episode_id,

            "received_time":
                event["received_time"],

            "event_time":
                event["event_time"],

            "event_kind":
                event["kind"],

            "local_update_id":
                local_update_id,

            "best_bid":
                best_bid,

            "best_ask":
                best_ask,

            "mid":
                mid,

            "spread":
                spread,

            "bid_levels":
                len(bids),

            "ask_levels":
                len(asks),

            "bid_depth_top5":
                bid_qty_5,

            "ask_depth_top5":
                ask_qty_5,

            "obi_top5":
                obi5,

            "crossed_book":
                crossed
        })


    # ------------------------------------------------------------------
    # REPLAY
    # ------------------------------------------------------------------

    for event in events:


        # ==============================================================
        # SNAPSHOT
        # ==============================================================

        if event["kind"] == "snapshot":

            load_snapshot(
                event["rows"]
            )

            snapshot_last_id = int(
                event["last_update_id"]
            )

            local_update_id = (
                snapshot_last_id
            )

            waiting_for_bridge = True
            book_valid = False

            snapshots_loaded += 1

            continue


        # ==============================================================
        # UPDATE
        # ==============================================================

        U = int(
            event["U"]
        )

        u = int(
            event["u"]
        )

        pu = int(
            event["pu"]
        )


        # ==============================================================
        # FRESH SNAPSHOT:
        # skip stale events then demand U <= snapshot+1 <= u
        # ==============================================================

        if waiting_for_bridge:

            if u <= snapshot_last_id:

                stale_updates_skipped += 1

                continue


            target = (
                snapshot_last_id
                +
                1
            )

            bridge_ok = (
                U
                <=
                target
                <=
                u
            )


            if not bridge_ok:

                invalid_bridges += 1

                book_valid = False
                waiting_for_bridge = False

                bids.clear()
                asks.clear()

                local_update_id = None
                snapshot_last_id = None

                continue


            valid_bridges += 1

            current_episode_id += 1

            apply_levels(
                event["rows"]
            )

            local_update_id = u

            waiting_for_bridge = False
            book_valid = True

            record_state(
                event
            )

            continue


        # ==============================================================
        # INVALID BOOK:
        # wait for next snapshot.
        # ==============================================================

        if not book_valid:
            continue


        # ==============================================================
        # CONTINUITY:
        # exact D06 condition.
        # ==============================================================

        if pu != local_update_id:

            sequence_failures += 1

            book_valid = False

            bids.clear()
            asks.clear()

            local_update_id = None

            continue


        # ==============================================================
        # VALID CONTINUOUS UPDATE
        # ==============================================================

        apply_levels(
            event["rows"]
        )

        local_update_id = u

        continuous_updates += 1

        record_state(
            event
        )


    states_df = pd.DataFrame(
        states
    )


    # ------------------------------------------------------------------
    # AUDIT
    # ------------------------------------------------------------------

    if len(states_df):

        crossed = int(
            states_df[
                "crossed_book"
            ].sum()
        )

        valid_episodes = int(
            states_df[
                "episode_id"
            ].nunique()
        )

        spread_mean = float(
            states_df[
                "spread"
            ].mean()
        )

        spread_median = float(
            states_df[
                "spread"
            ].median()
        )

        spread_max = float(
            states_df[
                "spread"
            ].max()
        )

    else:

        crossed = 0
        valid_episodes = 0

        spread_mean = float(
            "nan"
        )

        spread_median = float(
            "nan"
        )

        spread_max = float(
            "nan"
        )


    # ------------------------------------------------------------------
    # SAVE VALID STATES
    # ------------------------------------------------------------------

    state_file = (
        OUT_DIR
        /
        f"{hour}_canonical_book_states.csv"
    )

    states_df.to_csv(
        state_file,
        index=False
    )


    # ------------------------------------------------------------------
    # GATE RULE
    #
    # We do NOT require zero invalid bridges.
    # Discovery D06 itself had invalid bridges.
    #
    # Invalid sections are excluded by construction.
    # ------------------------------------------------------------------

    gate_pass = bool(
        valid_bridges > 0
        and
        len(states_df) > 0
        and
        valid_episodes > 0
        and
        crossed == 0
    )


    print()
    print(
        "SNAPSHOTS LOADED        :",
        f"{snapshots_loaded:,}"
    )

    print(
        "VALID SNAPSHOT BRIDGES  :",
        f"{valid_bridges:,}"
    )

    print(
        "INVALID BRIDGES         :",
        f"{invalid_bridges:,}"
    )

    print(
        "STALE UPDATES SKIPPED   :",
        f"{stale_updates_skipped:,}"
    )

    print(
        "CONTINUOUS UPDATES      :",
        f"{continuous_updates:,}"
    )

    print(
        "SEQUENCE FAILURES       :",
        f"{sequence_failures:,}"
    )

    print(
        "VALID STATES            :",
        f"{len(states_df):,}"
    )

    print(
        "VALID EPISODES          :",
        f"{valid_episodes:,}"
    )

    print(
        "CROSSED/LOCKED STATES   :",
        f"{crossed:,}"
    )

    print(
        "SPREAD MEAN             :",
        f"{spread_mean:.8f}"
    )

    print(
        "SPREAD MEDIAN           :",
        f"{spread_median:.8f}"
    )

    print(
        "SPREAD MAX              :",
        f"{spread_max:.8f}"
    )

    print()
    print(
        "CANONICAL GATE 1        :",
        "PASS"
        if gate_pass
        else
        "FAIL"
    )

    print(
        "SAVED STATES            :",
        state_file
    )


    result = {

        "hour":
            hour,

        "raw_rows":
            len(df),

        "snapshot_events":
            len(snapshot_groups),

        "update_events":
            len(update_groups),

        "snapshots_loaded":
            snapshots_loaded,

        "valid_snapshot_bridges":
            valid_bridges,

        "invalid_snapshot_bridges":
            invalid_bridges,

        "stale_updates_skipped":
            stale_updates_skipped,

        "continuous_updates":
            continuous_updates,

        "sequence_failures":
            sequence_failures,

        "valid_states":
            len(states_df),

        "valid_episodes":
            valid_episodes,

        "crossed_locked_states":
            crossed,

        "spread_mean":
            spread_mean,

        "spread_median":
            spread_median,

        "spread_max":
            spread_max,

        "gate1_pass":
            gate_pass,

        "states_file":
            str(state_file)
    }


    # Free memory before next hour.
    del df
    del snap_rows
    del upd_rows
    del snapshot_groups
    del update_groups
    del events
    del states_df

    return result


# ======================================================================
# RUN ALL FIVE UNTOUCHED HOURS
# ======================================================================

results = []


for hour in REPLICATION_HOURS:

    try:

        result = replay_hour(
            hour
        )

        results.append(
            result
        )

    except Exception as exc:

        print()
        print(
            "ERROR FOR",
            hour,
            ":",
            type(exc).__name__,
            str(exc)
        )

        results.append({

            "hour":
                hour,

            "gate1_pass":
                False,

            "error":
                type(exc).__name__
                + ": "
                + str(exc)
        })


summary = pd.DataFrame(
    results
)

summary.to_csv(
    SUMMARY_FILE,
    index=False
)


print()
print("=" * 110)
print("CANONICAL GATE 1 SUMMARY")
print("=" * 110)


wanted = [
    "hour",
    "snapshots_loaded",
    "valid_snapshot_bridges",
    "invalid_snapshot_bridges",
    "stale_updates_skipped",
    "continuous_updates",
    "sequence_failures",
    "valid_states",
    "valid_episodes",
    "crossed_locked_states",
    "gate1_pass",
]

available = [
    c for c in wanted
    if c in summary.columns
]

print(
    summary[
        available
    ].to_string(
        index=False
    )
)


print()
print(
    "PASS HOURS:",
    int(
        summary[
            "gate1_pass"
        ]
        .fillna(False)
        .sum()
    ),
    "/",
    len(summary)
)

print()
print(
    "SUMMARY SAVED:"
)

print(
    SUMMARY_FILE
)

print()
print("=" * 110)
print("CANONICAL GATE 1 COMPLETE")
print("=" * 110)
