import pandas as pd
import pyarrow.parquet as pq
import pyarrow as pa
import zstandard as zstd
import io
from pathlib import Path
import numpy as np

BOOK_FILE = Path(
    r"C:\Users\USER\Documents\Audit_V2_1\Raw_Orderbooks"
    r"\BTCUSDT_orderbook_2026-05-25_00.parquet"
)

OUT_FILE = Path(
    r"C:\Users\USER\Documents\d07_liquidity_event_tape.csv"
)

print("=" * 100)
print("CRYPTOHFT D07 - VALID L2 LIQUIDITY EVENT TAPE")
print("=" * 100)


# =====================================================================
# LOAD CRYPTOHFT PARQUET
# =====================================================================

def read_cryptohft(path):

    with open(path, "rb") as f:
        sig = f.read(4)

    if sig == b"PAR1":
        return pd.read_parquet(path)

    if sig == b"\x28\xb5\x2f\xfd":

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
        f"Unknown signature: {sig!r}"
    )


df = read_cryptohft(BOOK_FILE)

print()
print("PRICE-LEVEL ROWS:", f"{len(df):,}")


# =====================================================================
# NORMALIZE
# =====================================================================

df["event_type"] = (
    df["event_type"]
    .astype(str)
    .str.lower()
)

df["side"] = (
    df["side"]
    .astype(str)
    .str.lower()
)

df["price_num"] = pd.to_numeric(
    df["price"],
    errors="raise"
)

df["qty_num"] = pd.to_numeric(
    df["quantity"],
    errors="raise"
)


# =====================================================================
# SNAPSHOT EVENTS
# =====================================================================

snap = df[
    df["event_type"] == "snapshot"
]

snapshots = []

for key, g in snap.groupby(
    [
        "received_time",
        "event_time",
        "last_update_id"
    ],
    sort=False,
    dropna=False
):

    recv, evt, last_id = key

    snapshots.append({
        "kind": "snapshot",
        "received_time": int(recv),
        "event_time": int(evt),
        "last_update_id": int(last_id),
        "rows": g
    })


# =====================================================================
# UPDATE EVENTS
# =====================================================================

upd = df[
    df["event_type"] == "update"
]

updates = []

for key, g in upd.groupby(
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
        recv,
        evt,
        tx,
        U,
        u,
        pu
    ) = key

    updates.append({
        "kind": "update",
        "received_time": int(recv),
        "event_time": int(evt),
        "transaction_time": int(tx),
        "U": int(U),
        "u": int(u),
        "pu": int(pu),
        "rows": g
    })


events = snapshots + updates

events.sort(
    key=lambda x: (
        x["received_time"],
        0 if x["kind"] == "snapshot" else 1,
        x.get(
            "u",
            x.get("last_update_id", 0)
        )
    )
)

print("SNAPSHOTS       :", f"{len(snapshots):,}")
print("UPDATE EVENTS   :", f"{len(updates):,}")


# =====================================================================
# LOCAL BOOK
# =====================================================================

bids = {}
asks = {}

book_valid = False
waiting_bridge = False

snapshot_last_id = None
local_update_id = None

episode_id = 0

records = []

valid_bridges = 0
invalid_bridges = 0
sequence_failures = 0
stale_skipped = 0


# =====================================================================
# SNAPSHOT LOADER
# =====================================================================

def load_snapshot(rows):

    bids.clear()
    asks.clear()

    for r in rows.itertuples(index=False):

        p = float(r.price_num)
        q = float(r.qty_num)

        if q <= 0:
            continue

        if r.side == "bid":
            bids[p] = q

        elif r.side == "ask":
            asks[p] = q


# =====================================================================
# DEPTH FUNCTIONS
# =====================================================================

def top_depth(book, side, n):

    if side == "bid":
        levels = sorted(
            book.items(),
            reverse=True
        )[:n]
    else:
        levels = sorted(
            book.items()
        )[:n]

    return sum(
        q for _, q in levels
    )


# =====================================================================
# APPLY UPDATE + MEASURE CHANGE
# =====================================================================

def apply_and_measure(rows):

    bid_add = 0.0
    ask_add = 0.0

    bid_remove = 0.0
    ask_remove = 0.0

    bid_full_delete = 0.0
    ask_full_delete = 0.0

    bid_levels_added = 0
    ask_levels_added = 0

    bid_levels_removed = 0
    ask_levels_removed = 0

    bid_levels_modified = 0
    ask_levels_modified = 0

    for r in rows.itertuples(index=False):

        side = r.side
        p = float(r.price_num)
        new_q = float(r.qty_num)

        book = bids if side == "bid" else asks

        old_q = float(
            book.get(p, 0.0)
        )

        delta = new_q - old_q

        # ---------------------------------------------------------
        # QUANTITY INCREASE
        # ---------------------------------------------------------

        if delta > 0:

            if side == "bid":
                bid_add += delta
            else:
                ask_add += delta

            if old_q == 0:

                if side == "bid":
                    bid_levels_added += 1
                else:
                    ask_levels_added += 1

            else:

                if side == "bid":
                    bid_levels_modified += 1
                else:
                    ask_levels_modified += 1


        # ---------------------------------------------------------
        # QUANTITY DECREASE
        # ---------------------------------------------------------

        elif delta < 0:

            removed = abs(delta)

            if side == "bid":
                bid_remove += removed
            else:
                ask_remove += removed

            if new_q == 0:

                if side == "bid":
                    bid_full_delete += removed
                    bid_levels_removed += 1
                else:
                    ask_full_delete += removed
                    ask_levels_removed += 1

            else:

                if side == "bid":
                    bid_levels_modified += 1
                else:
                    ask_levels_modified += 1


        # ---------------------------------------------------------
        # APPLY NEW STATE
        # ---------------------------------------------------------

        if new_q == 0:

            book.pop(
                p,
                None
            )

        else:

            book[p] = new_q


    return {
        "bid_add_qty": bid_add,
        "ask_add_qty": ask_add,

        "bid_remove_qty": bid_remove,
        "ask_remove_qty": ask_remove,

        "bid_full_delete_qty": bid_full_delete,
        "ask_full_delete_qty": ask_full_delete,

        "bid_levels_added": bid_levels_added,
        "ask_levels_added": ask_levels_added,

        "bid_levels_removed": bid_levels_removed,
        "ask_levels_removed": ask_levels_removed,

        "bid_levels_modified": bid_levels_modified,
        "ask_levels_modified": ask_levels_modified
    }


# =====================================================================
# REPLAY
# =====================================================================

print()
print("Replaying valid episodes...")

for event in events:

    # ---------------------------------------------------------
    # SNAPSHOT
    # ---------------------------------------------------------

    if event["kind"] == "snapshot":

        load_snapshot(
            event["rows"]
        )

        snapshot_last_id = int(
            event["last_update_id"]
        )

        local_update_id = snapshot_last_id

        waiting_bridge = True
        book_valid = False

        continue


    U = int(event["U"])
    u = int(event["u"])
    pu = int(event["pu"])


    # ---------------------------------------------------------
    # SNAPSHOT -> FIRST APPLICABLE UPDATE
    # ---------------------------------------------------------

    if waiting_bridge:

        if u <= snapshot_last_id:

            stale_skipped += 1
            continue

        target = snapshot_last_id + 1

        if not (
            U <= target <= u
        ):

            invalid_bridges += 1

            waiting_bridge = False
            book_valid = False

            bids.clear()
            asks.clear()

            local_update_id = None
            snapshot_last_id = None

            continue


        # NEW VERIFIED EPISODE

        episode_id += 1

        valid_bridges += 1

        before_bid = max(bids)
        before_ask = min(asks)

        before_mid = (
            before_bid + before_ask
        ) / 2.0

        before_bid_depth5 = top_depth(
            bids,
            "bid",
            5
        )

        before_ask_depth5 = top_depth(
            asks,
            "ask",
            5
        )

        changes = apply_and_measure(
            event["rows"]
        )

        local_update_id = u
        waiting_bridge = False
        book_valid = True


    else:

        if not book_valid:
            continue

        # -----------------------------------------------------
        # UPDATE -> UPDATE CONTINUITY
        # -----------------------------------------------------

        if pu != local_update_id:

            sequence_failures += 1

            book_valid = False

            bids.clear()
            asks.clear()

            local_update_id = None

            continue


        before_bid = max(bids)
        before_ask = min(asks)

        before_mid = (
            before_bid + before_ask
        ) / 2.0

        before_bid_depth5 = top_depth(
            bids,
            "bid",
            5
        )

        before_ask_depth5 = top_depth(
            asks,
            "ask",
            5
        )

        changes = apply_and_measure(
            event["rows"]
        )

        local_update_id = u


    # ---------------------------------------------------------
    # VALID POST-UPDATE STATE
    # ---------------------------------------------------------

    if not bids or not asks:
        continue

    best_bid = max(bids)
    best_ask = min(asks)

    mid = (
        best_bid + best_ask
    ) / 2.0

    spread = (
        best_ask - best_bid
    )

    bid_depth5 = top_depth(
        bids,
        "bid",
        5
    )

    ask_depth5 = top_depth(
        asks,
        "ask",
        5
    )

    depth_denom = (
        bid_depth5 +
        ask_depth5
    )

    if depth_denom > 0:

        obi5 = (
            bid_depth5 -
            ask_depth5
        ) / depth_denom

    else:

        obi5 = np.nan


    # ---------------------------------------------------------
    # EVENT-LEVEL ECOLOGY MEASURES
    # ---------------------------------------------------------

    total_add = (
        changes["bid_add_qty"] +
        changes["ask_add_qty"]
    )

    total_remove = (
        changes["bid_remove_qty"] +
        changes["ask_remove_qty"]
    )

    liquidity_net = (
        total_add -
        total_remove
    )

    # Positive = bid-side net support relative to ask-side.
    directional_liquidity = (
        changes["bid_add_qty"]
        - changes["bid_remove_qty"]
        - changes["ask_add_qty"]
        + changes["ask_remove_qty"]
    )

    records.append({

        "episode_id": episode_id,

        "received_time_ns":
            event["received_time"],

        "event_time_ms":
            event["event_time"],

        "transaction_time_ms":
            event["transaction_time"],

        "first_update_id": U,
        "final_update_id": u,
        "prev_final_update_id": pu,

        "changed_levels":
            len(event["rows"]),

        "best_bid_before":
            before_bid,

        "best_ask_before":
            before_ask,

        "mid_before":
            before_mid,

        "best_bid_after":
            best_bid,

        "best_ask_after":
            best_ask,

        "mid_after":
            mid,

        "mid_change":
            mid - before_mid,

        "spread_after":
            spread,

        "bid_depth5_before":
            before_bid_depth5,

        "ask_depth5_before":
            before_ask_depth5,

        "bid_depth5_after":
            bid_depth5,

        "ask_depth5_after":
            ask_depth5,

        "obi5_after":
            obi5,

        **changes,

        "total_add_qty":
            total_add,

        "total_remove_qty":
            total_remove,

        "net_displayed_liquidity":
            liquidity_net,

        "directional_liquidity":
            directional_liquidity,

        "crossed_book":
            int(best_bid >= best_ask)
    })


# =====================================================================
# OUTPUT
# =====================================================================

out = pd.DataFrame(records)

if len(out):

    out["event_time_utc"] = pd.to_datetime(
        out["event_time_ms"],
        unit="ms",
        utc=True
    )

    out["transaction_time_utc"] = pd.to_datetime(
        out["transaction_time_ms"],
        unit="ms",
        utc=True
    )


print()
print("=" * 100)
print("D07 RESULTS")
print("=" * 100)

print(
    "VALID BRIDGES        :",
    f"{valid_bridges:,}"
)

print(
    "INVALID BRIDGES      :",
    f"{invalid_bridges:,}"
)

print(
    "STALE SKIPPED        :",
    f"{stale_skipped:,}"
)

print(
    "SEQUENCE FAILURES    :",
    f"{sequence_failures:,}"
)

print(
    "VALID EVENT RECORDS  :",
    f"{len(out):,}"
)

if len(out):

    print(
        "VALID EPISODES       :",
        f"{out['episode_id'].nunique():,}"
    )

    print(
        "CROSSED STATES       :",
        f"{int(out['crossed_book'].sum()):,}"
    )

    print()
    print("DISPLAYED LIQUIDITY QUANTITY")

    print(
        "BID ADD TOTAL        :",
        round(
            out["bid_add_qty"].sum(),
            6
        )
    )

    print(
        "ASK ADD TOTAL        :",
        round(
            out["ask_add_qty"].sum(),
            6
        )
    )

    print(
        "BID REMOVE TOTAL     :",
        round(
            out["bid_remove_qty"].sum(),
            6
        )
    )

    print(
        "ASK REMOVE TOTAL     :",
        round(
            out["ask_remove_qty"].sum(),
            6
        )
    )

    print()
    print("MIDPRICE MOVEMENT")

    moved = (
        out["mid_change"] != 0
    )

    print(
        "EVENTS MOVING MID    :",
        f"{int(moved.sum()):,}"
    )

    print(
        "MID MOVE RATE        :",
        f"{moved.mean():.6f}"
    )

    print()
    print("SPREAD DISTRIBUTION")

    print(
        out["spread_after"]
        .describe()
        .to_string()
    )

    print()
    print("LARGEST SPREAD EVENTS")

    cols = [
        "event_time_utc",
        "episode_id",
        "spread_after",
        "mid_before",
        "mid_after",
        "total_add_qty",
        "total_remove_qty"
    ]

    print(
        out.nlargest(
            10,
            "spread_after"
        )[cols].to_string(
            index=False
        )
    )

    print()
    print("LIQUIDITY EVENT SUMMARY")

    cols2 = [
        "bid_add_qty",
        "ask_add_qty",
        "bid_remove_qty",
        "ask_remove_qty",
        "total_add_qty",
        "total_remove_qty",
        "net_displayed_liquidity",
        "directional_liquidity"
    ]

    print(
        out[cols2]
        .describe()
        .to_string()
    )

    out.to_csv(
        OUT_FILE,
        index=False
    )

    print()
    print("SAVED:")
    print(OUT_FILE)


print()
print("=" * 100)
print("D07 COMPLETE")
print("=" * 100)
