import pandas as pd
import pyarrow.parquet as pq
import pyarrow as pa
import zstandard as zstd
import io
from pathlib import Path
from collections import defaultdict

BOOK_FILE = Path(
    r"C:\Users\USER\Documents\Audit_V2_1\Raw_Orderbooks"
    r"\BTCUSDT_orderbook_2026-05-25_00.parquet"
)

OUT_FILE = Path(
    r"C:\Users\USER\Documents\d06_reconstructed_book_states.csv"
)

print("=" * 100)
print("CRYPTOHFT D06 - SNAPSHOT BRIDGE VALIDATION + DETERMINISTIC L2 REPLAY")
print("=" * 100)


# ============================================================
# READ OUTER-ZSTD PARQUET
# ============================================================

def read_cryptohft(path):

    with open(path, "rb") as f:
        first4 = f.read(4)

    if first4 == b"PAR1":
        return pd.read_parquet(path)

    if first4 == b"\x28\xb5\x2f\xfd":

        with open(path, "rb") as f:
            compressed = f.read()

        dctx = zstd.ZstdDecompressor()

        with dctx.stream_reader(
            io.BytesIO(compressed)
        ) as reader:
            raw = reader.read()

        if raw[:4] != b"PAR1":
            raise RuntimeError("Inner payload is not Parquet")

        return pq.read_table(
            pa.BufferReader(raw)
        ).to_pandas()

    raise RuntimeError(
        f"Unknown file signature: {first4!r}"
    )


df = read_cryptohft(BOOK_FILE)

print()
print("ROWS LOADED:", f"{len(df):,}")


# ============================================================
# NUMERIC CONVERSION
# ============================================================

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


# ============================================================
# BUILD LOGICAL SNAPSHOT EVENTS
# ============================================================

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

    received_time, event_time, last_update_id = key

    snapshot_groups.append({
        "received_time": int(received_time),
        "event_time": int(event_time),
        "last_update_id": int(last_update_id),
        "rows": g
    })


# ============================================================
# BUILD LOGICAL UPDATE EVENTS
# ============================================================

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
        "received_time": int(received_time),
        "event_time": int(event_time),
        "transaction_time": int(transaction_time),
        "U": int(first_update_id),
        "u": int(final_update_id),
        "pu": int(prev_final_update_id),
        "rows": g
    })


print("SNAPSHOT EVENTS:", f"{len(snapshot_groups):,}")
print("UPDATE EVENTS  :", f"{len(update_groups):,}")


# ============================================================
# COMBINE EVENTS IN RECEIVED-TIME ORDER
#
# Tie handling:
# snapshots come before updates when received_time matches,
# while update events sharing a timestamp are ordered by u.
# ============================================================

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
        (
            x.get("u", x.get("last_update_id", 0))
        )
    )
)


# ============================================================
# LOCAL ORDER BOOK
# ============================================================

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


def apply_levels(rows):

    global level_inserts
    global level_updates
    global level_deletes

    for row in rows.itertuples(index=False):

        side = row.side
        price = float(row.price_num)
        qty = float(row.qty_num)

        book = bids if side == "bid" else asks

        old_qty = book.get(price)

        if qty == 0.0:

            if price in book:
                del book[price]
                level_deletes += 1

        else:

            if old_qty is None:
                level_inserts += 1
            else:
                level_updates += 1

            book[price] = qty


def load_snapshot(rows):

    bids.clear()
    asks.clear()

    for row in rows.itertuples(index=False):

        price = float(row.price_num)
        qty = float(row.qty_num)

        if qty <= 0:
            continue

        if row.side == "bid":
            bids[price] = qty

        elif row.side == "ask":
            asks[price] = qty


def record_state(event):

    if not bids or not asks:
        return

    best_bid = max(bids)
    best_ask = min(asks)

    if best_ask <= best_bid:
        crossed = 1
    else:
        crossed = 0

    bid_qty_5 = 0.0
    ask_qty_5 = 0.0

    top_bids = sorted(
        bids.items(),
        reverse=True
    )[:5]

    top_asks = sorted(
        asks.items()
    )[:5]

    for _, q in top_bids:
        bid_qty_5 += q

    for _, q in top_asks:
        ask_qty_5 += q

    denom = bid_qty_5 + ask_qty_5

    if denom > 0:
        obi5 = (
            bid_qty_5 - ask_qty_5
        ) / denom
    else:
        obi5 = float("nan")

    mid = (
        best_bid + best_ask
    ) / 2.0

    spread = (
        best_ask - best_bid
    )

    states.append({
        "received_time": event["received_time"],
        "event_time": event["event_time"],
        "event_kind": event["kind"],
        "local_update_id": local_update_id,
        "best_bid": best_bid,
        "best_ask": best_ask,
        "mid": mid,
        "spread": spread,
        "bid_levels": len(bids),
        "ask_levels": len(asks),
        "bid_depth_top5": bid_qty_5,
        "ask_depth_top5": ask_qty_5,
        "obi_top5": obi5,
        "crossed_book": crossed
    })


# ============================================================
# REPLAY
# ============================================================

print()
print("Beginning deterministic replay...")

for event in events:

    # --------------------------------------------------------
    # SNAPSHOT
    # --------------------------------------------------------

    if event["kind"] == "snapshot":

        load_snapshot(
            event["rows"]
        )

        snapshot_last_id = int(
            event["last_update_id"]
        )

        local_update_id = snapshot_last_id

        waiting_for_bridge = True
        book_valid = False

        snapshots_loaded += 1

        continue


    # --------------------------------------------------------
    # UPDATE
    # --------------------------------------------------------

    U = int(event["U"])
    u = int(event["u"])
    pu = int(event["pu"])


    # --------------------------------------------------------
    # We have a freshly loaded snapshot.
    #
    # Ignore updates completely older than snapshot.
    #
    # Then require the first applicable event to bridge
    # snapshot_last_id + 1.
    # --------------------------------------------------------

    if waiting_for_bridge:

        if u <= snapshot_last_id:
            stale_updates_skipped += 1
            continue

        target = snapshot_last_id + 1

        bridge_ok = (
            U <= target <= u
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

        apply_levels(
            event["rows"]
        )

        local_update_id = u

        waiting_for_bridge = False
        book_valid = True

        record_state(event)

        continue


    # --------------------------------------------------------
    # No valid book available.
    # Wait for the next snapshot.
    # --------------------------------------------------------

    if not book_valid:
        continue


    # --------------------------------------------------------
    # CONTINUOUS UPDATE CHECK
    #
    # CryptoHFT exposes prev_final_update_id specifically
    # for continuity checking.
    # --------------------------------------------------------

    if pu != local_update_id:

        sequence_failures += 1

        book_valid = False

        bids.clear()
        asks.clear()

        local_update_id = None

        continue


    # --------------------------------------------------------
    # APPLY VALID EVENT
    # --------------------------------------------------------

    apply_levels(
        event["rows"]
    )

    local_update_id = u

    continuous_updates += 1

    record_state(event)


# ============================================================
# OUTPUT
# ============================================================

states_df = pd.DataFrame(states)

print()
print("=" * 100)
print("D06 REPLAY RESULTS")
print("=" * 100)

print(
    "SNAPSHOTS LOADED       :",
    f"{snapshots_loaded:,}"
)

print(
    "VALID SNAPSHOT BRIDGES :",
    f"{valid_bridges:,}"
)

print(
    "INVALID BRIDGES        :",
    f"{invalid_bridges:,}"
)

print(
    "STALE UPDATES SKIPPED  :",
    f"{stale_updates_skipped:,}"
)

print(
    "CONTINUOUS UPDATES     :",
    f"{continuous_updates:,}"
)

print(
    "SEQUENCE FAILURES      :",
    f"{sequence_failures:,}"
)

print(
    "VALID STATES RECORDED  :",
    f"{len(states_df):,}"
)

print()
print("LEVEL EVENT COUNTS")

print(
    "INSERTS                :",
    f"{level_inserts:,}"
)

print(
    "QUANTITY UPDATES       :",
    f"{level_updates:,}"
)

print(
    "DELETES                :",
    f"{level_deletes:,}"
)


if len(states_df):

    crossed = int(
        states_df["crossed_book"].sum()
    )

    print()
    print(
        "CROSSED/LOCKED STATES  :",
        f"{crossed:,}"
    )

    print(
        "CROSSED RATE           :",
        f"{crossed / len(states_df):.8f}"
    )

    print()
    print("SPREAD SUMMARY")

    print(
        states_df["spread"]
        .describe()
        .to_string()
    )

    print()
    print("MIDPRICE SUMMARY")

    print(
        states_df["mid"]
        .describe()
        .to_string()
    )

    print()
    print("TOP-5 OBI SUMMARY")

    print(
        states_df["obi_top5"]
        .describe()
        .to_string()
    )

    print()
    print("FIRST 10 VALID STATES")

    print(
        states_df.head(10)
        .to_string(index=False)
    )

    states_df.to_csv(
        OUT_FILE,
        index=False
    )

    print()
    print("SAVED:")
    print(OUT_FILE)


print()
print("=" * 100)
print("D06 COMPLETE")
print("=" * 100)
