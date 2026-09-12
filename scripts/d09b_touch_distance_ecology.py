import pandas as pd
import numpy as np
import pyarrow.parquet as pq
import pyarrow as pa
import zstandard as zstd
import io
from pathlib import Path


RAW_BOOK = Path(
    r"C:\Users\USER\Documents\Audit_V2_1\Raw_Orderbooks"
    r"\BTCUSDT_orderbook_2026-05-25_00.parquet"
)

D09_FILE = Path(
    r"C:\Users\USER\Documents\d09_joint_flow_liquidity_tape.csv"
)

EVENT_OUT = Path(
    r"C:\Users\USER\Documents\d09b_touch_distance_book_events.csv"
)

JOINT_OUT = Path(
    r"C:\Users\USER\Documents\d09b_joint_flow_touch_ecology.csv"
)


print("=" * 112)
print("CRYPTOHFT D09B - DISTANCE-FROM-TOUCH LIQUIDITY ECOLOGY")
print("=" * 112)


# =====================================================================
# LOAD OUTER-ZSTD PARQUET
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


# =====================================================================
# LOAD RAW BOOK
# =====================================================================

df = read_cryptohft(
    RAW_BOOK
)

print()
print(
    "RAW PRICE-LEVEL ROWS:",
    f"{len(df):,}"
)


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
# INFER PRICE TICK FROM FIRST SNAPSHOT
# =====================================================================

snap_sample = (
    df[df["event_type"] == "snapshot"]
    .head(1000)
)

sample_prices = np.sort(
    snap_sample["price_num"].unique()
)

diffs = np.diff(
    sample_prices
)

diffs = diffs[
    diffs > 1e-9
]

if len(diffs) == 0:
    raise RuntimeError(
        "Could not infer tick size."
    )

tick_size = float(
    np.min(diffs)
)

print(
    "INFERRED PRICE TICK:",
    tick_size
)


# =====================================================================
# BUILD LOGICAL SNAPSHOT EVENTS
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

        "kind":
            "snapshot",

        "received_time":
            int(recv),

        "event_time":
            int(evt),

        "last_update_id":
            int(last_id),

        "rows":
            g
    })


# =====================================================================
# BUILD LOGICAL UPDATE EVENTS
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

    recv, evt, tx, U, u, pu = key

    updates.append({

        "kind":
            "update",

        "received_time":
            int(recv),

        "event_time":
            int(evt),

        "transaction_time":
            int(tx),

        "U":
            int(U),

        "u":
            int(u),

        "pu":
            int(pu),

        "rows":
            g
    })


events = snapshots + updates

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


print(
    "SNAPSHOT EVENTS:",
    f"{len(snapshots):,}"
)

print(
    "UPDATE EVENTS  :",
    f"{len(updates):,}"
)


# =====================================================================
# BOOK STATE
# =====================================================================

bids = {}
asks = {}

book_valid = False
waiting_bridge = False

snapshot_last_id = None
local_update_id = None

episode_id = 0

valid_bridges = 0
invalid_bridges = 0
stale_skipped = 0
sequence_failures = 0

records = []


# =====================================================================
# LOAD SNAPSHOT
# =====================================================================

def load_snapshot(rows):

    bids.clear()
    asks.clear()

    for r in rows.itertuples(index=False):

        p = float(
            r.price_num
        )

        q = float(
            r.qty_num
        )

        if q <= 0:
            continue

        if r.side == "bid":
            bids[p] = q

        elif r.side == "ask":
            asks[p] = q


# =====================================================================
# DISTANCE BUCKET
# =====================================================================

def get_distance_bucket(
    side,
    price,
    best_bid,
    best_ask
):

    if side == "ask":

        raw_ticks = (
            price - best_ask
        ) / tick_size

    else:

        raw_ticks = (
            best_bid - price
        ) / tick_size


    # A new price improving the current touch produces
    # a negative raw distance.
    #
    # Economically it belongs at the touch, so clamp to zero.

    ticks = max(
        0,
        int(
            round(
                raw_ticks
            )
        )
    )


    if ticks <= 5:

        bucket = "0_5"

    elif ticks <= 20:

        bucket = "6_20"

    else:

        bucket = "gt20"


    return ticks, bucket


# =====================================================================
# EMPTY RESPONSE COUNTERS
# =====================================================================

def blank_changes():

    d = {}

    for side in [
        "bid",
        "ask"
    ]:

        for action in [
            "add",
            "remove"
        ]:

            for bucket in [
                "0_5",
                "6_20",
                "gt20"
            ]:

                d[
                    f"{side}_{action}_{bucket}_qty"
                ] = 0.0

                d[
                    f"{side}_{action}_{bucket}_levels"
                ] = 0

    d[
        "price_improving_bid_updates"
    ] = 0

    d[
        "price_improving_ask_updates"
    ] = 0

    return d


# =====================================================================
# APPLY UPDATE AND CLASSIFY BY DISTANCE
# =====================================================================

def apply_and_classify(
    rows,
    best_bid_before,
    best_ask_before
):

    ch = blank_changes()

    for r in rows.itertuples(
        index=False
    ):

        side = r.side

        p = float(
            r.price_num
        )

        new_q = float(
            r.qty_num
        )

        book = (
            bids
            if side == "bid"
            else asks
        )

        old_q = float(
            book.get(
                p,
                0.0
            )
        )

        delta = (
            new_q - old_q
        )


        # -------------------------------------------------------------
        # DISTANCE FROM PRE-EVENT TOUCH
        # -------------------------------------------------------------

        ticks, bucket = (
            get_distance_bucket(
                side,
                p,
                best_bid_before,
                best_ask_before
            )
        )


        # -------------------------------------------------------------
        # PRICE-IMPROVING LEVEL
        # -------------------------------------------------------------

        if side == "bid":

            if p > best_bid_before:

                ch[
                    "price_improving_bid_updates"
                ] += 1

        else:

            if p < best_ask_before:

                ch[
                    "price_improving_ask_updates"
                ] += 1


        # -------------------------------------------------------------
        # ADDITION / INCREASE
        # -------------------------------------------------------------

        if delta > 0:

            ch[
                f"{side}_add_{bucket}_qty"
            ] += delta

            ch[
                f"{side}_add_{bucket}_levels"
            ] += 1


        # -------------------------------------------------------------
        # DECREASE / REMOVAL
        # -------------------------------------------------------------

        elif delta < 0:

            removed = abs(
                delta
            )

            ch[
                f"{side}_remove_{bucket}_qty"
            ] += removed

            ch[
                f"{side}_remove_{bucket}_levels"
            ] += 1


        # -------------------------------------------------------------
        # APPLY BOOK STATE
        # -------------------------------------------------------------

        if new_q == 0:

            book.pop(
                p,
                None
            )

        else:

            book[p] = new_q


    return ch


# =====================================================================
# REPLAY
# =====================================================================

print()
print(
    "Beginning replay + touch-distance classification..."
)


for event in events:

    # -------------------------------------------------------------
    # SNAPSHOT
    # -------------------------------------------------------------

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

        waiting_bridge = True
        book_valid = False

        continue


    U = int(
        event["U"]
    )

    u = int(
        event["u"]
    )

    pu = int(
        event["pu"]
    )


    # -------------------------------------------------------------
    # FIRST UPDATE AFTER SNAPSHOT
    # -------------------------------------------------------------

    if waiting_bridge:

        if u <= snapshot_last_id:

            stale_skipped += 1
            continue


        target = (
            snapshot_last_id + 1
        )

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


        episode_id += 1
        valid_bridges += 1

        book_valid = True
        waiting_bridge = False


    else:

        if not book_valid:
            continue


        if pu != local_update_id:

            sequence_failures += 1

            book_valid = False

            bids.clear()
            asks.clear()

            local_update_id = None

            continue


    if not bids or not asks:
        continue


    # -------------------------------------------------------------
    # PRE-EVENT TOUCH
    # -------------------------------------------------------------

    best_bid_before = max(
        bids
    )

    best_ask_before = min(
        asks
    )

    mid_before = (
        best_bid_before +
        best_ask_before
    ) / 2.0


    # -------------------------------------------------------------
    # APPLY + CLASSIFY
    # -------------------------------------------------------------

    changes = apply_and_classify(

        event["rows"],

        best_bid_before,
        best_ask_before
    )


    local_update_id = u


    if not bids or not asks:

        book_valid = False
        continue


    # -------------------------------------------------------------
    # POST-EVENT STATE
    # -------------------------------------------------------------

    best_bid_after = max(
        bids
    )

    best_ask_after = min(
        asks
    )

    mid_after = (
        best_bid_after +
        best_ask_after
    ) / 2.0


    row = {

        "episode_id":
            episode_id,

        "event_time_ms":
            int(
                event["event_time"]
            ),

        "transaction_time_ms":
            int(
                event["transaction_time"]
            ),

        "received_time_ns":
            int(
                event["received_time"]
            ),

        "first_update_id":
            U,

        "final_update_id":
            u,

        "prev_final_update_id":
            pu,

        "best_bid_before":
            best_bid_before,

        "best_ask_before":
            best_ask_before,

        "best_bid_after":
            best_bid_after,

        "best_ask_after":
            best_ask_after,

        "mid_before":
            mid_before,

        "mid_after":
            mid_after,

        "mid_change":
            mid_after - mid_before,

        **changes
    }


    # -------------------------------------------------------------
    # NET RESPONSE BY SIDE / DISTANCE
    # -------------------------------------------------------------

    for side in [
        "bid",
        "ask"
    ]:

        for bucket in [
            "0_5",
            "6_20",
            "gt20"
        ]:

            row[
                f"{side}_net_{bucket}_qty"
            ] = (

                row[
                    f"{side}_add_{bucket}_qty"
                ]

                -

                row[
                    f"{side}_remove_{bucket}_qty"
                ]
            )


    records.append(
        row
    )


# =====================================================================
# EVENT TABLE
# =====================================================================

evt = pd.DataFrame(
    records
)


print()
print("=" * 112)
print("D09B REPLAY AUDIT")
print("=" * 112)

print(
    "VALID BRIDGES       :",
    f"{valid_bridges:,}"
)

print(
    "INVALID BRIDGES     :",
    f"{invalid_bridges:,}"
)

print(
    "STALE SKIPPED       :",
    f"{stale_skipped:,}"
)

print(
    "SEQUENCE FAILURES   :",
    f"{sequence_failures:,}"
)

print(
    "VALID EVENT RECORDS :",
    f"{len(evt):,}"
)


# =====================================================================
# DISTANCE TOTALS
# =====================================================================

print()
print("=" * 112)
print("DISPLAYED LIQUIDITY BY DISTANCE FROM PRE-EVENT TOUCH")
print("=" * 112)


for bucket in [
    "0_5",
    "6_20",
    "gt20"
]:

    print()
    print(
        "BUCKET:",
        bucket
    )

    for side in [
        "bid",
        "ask"
    ]:

        add = evt[
            f"{side}_add_{bucket}_qty"
        ].sum()

        remove = evt[
            f"{side}_remove_{bucket}_qty"
        ].sum()

        net = (
            add - remove
        )

        print(
            f"{side.upper():3s} "
            f"ADD={add:12.6f}  "
            f"REMOVE={remove:12.6f}  "
            f"NET={net:12.6f}"
        )


print()
print(
    "PRICE-IMPROVING BID UPDATES:",
    f"{int(evt['price_improving_bid_updates'].sum()):,}"
)

print(
    "PRICE-IMPROVING ASK UPDATES:",
    f"{int(evt['price_improving_ask_updates'].sum()):,}"
)


# =====================================================================
# SAVE EVENT DATA
# =====================================================================

evt["event_time_utc"] = pd.to_datetime(
    evt["event_time_ms"],
    unit="ms",
    utc=True
)

evt.to_csv(
    EVENT_OUT,
    index=False
)


# =====================================================================
# MERGE INTO D09 JOINT FLOW TAPE
# =====================================================================

joint = pd.read_csv(
    D09_FILE
)

joint["episode_id"] = pd.to_numeric(
    joint["episode_id"],
    errors="raise"
).astype("int64")

joint["t1_event_time_ms"] = pd.to_numeric(
    joint["t1_event_time_ms"],
    errors="raise"
).astype("int64")


touch_cols = [

    "episode_id",
    "event_time_ms",

    "bid_add_0_5_qty",
    "bid_remove_0_5_qty",
    "bid_net_0_5_qty",

    "ask_add_0_5_qty",
    "ask_remove_0_5_qty",
    "ask_net_0_5_qty",

    "bid_add_6_20_qty",
    "bid_remove_6_20_qty",
    "bid_net_6_20_qty",

    "ask_add_6_20_qty",
    "ask_remove_6_20_qty",
    "ask_net_6_20_qty",

    "bid_add_gt20_qty",
    "bid_remove_gt20_qty",
    "bid_net_gt20_qty",

    "ask_add_gt20_qty",
    "ask_remove_gt20_qty",
    "ask_net_gt20_qty",

    "price_improving_bid_updates",
    "price_improving_ask_updates"
]


aug = joint.merge(

    evt[touch_cols],

    left_on=[
        "episode_id",
        "t1_event_time_ms"
    ],

    right_on=[
        "episode_id",
        "event_time_ms"
    ],

    how="left",

    validate="many_to_one"
)


match_rate = (
    aug["event_time_ms"]
    .notna()
    .mean()
)


print()
print("=" * 112)
print("D09 -> D09B MERGE")
print("=" * 112)

print(
    "D09 ROWS              :",
    f"{len(joint):,}"
)

print(
    "AUGMENTED ROWS        :",
    f"{len(aug):,}"
)

print(
    "TOUCH RESPONSE MATCH  :",
    f"{match_rate:.8f}"
)


# =====================================================================
# PRIMARY CLEAN SUBSET
#
# Exclude intervals containing a trade exactly at t1 because
# exchange millisecond timestamps do not reveal within-ms ordering.
# =====================================================================

clean = aug[
    aug["trades_exactly_at_t1"] == 0
].copy()


print()
print("=" * 112)
print("PRIMARY TIMESTAMP-CLEAN SAMPLE")
print("=" * 112)

print(
    "ALL INTERVALS:",
    f"{len(aug):,}"
)

print(
    "CLEAN INTERVALS:",
    f"{len(clean):,}"
)

print(
    "REMOVED FOR EXACT-t1 AMBIGUITY:",
    f"{len(aug) - len(clean):,}"
)


flow_clean = clean[
    clean["total_flow_qty"] > 0
]


print(
    "CLEAN FLOW INTERVALS:",
    f"{len(flow_clean):,}"
)


# =====================================================================
# NEAR-TOUCH RESPONSE IN FLOW INTERVALS
# =====================================================================

if len(flow_clean):

    print()
    print("=" * 112)
    print("NEAR-TOUCH RESPONSE - FLOW INTERVALS ONLY")
    print("=" * 112)

    cols = [

        "bid_add_0_5_qty",
        "bid_remove_0_5_qty",
        "bid_net_0_5_qty",

        "ask_add_0_5_qty",
        "ask_remove_0_5_qty",
        "ask_net_0_5_qty"
    ]

    print(
        flow_clean[cols]
        .describe(
            percentiles=[
                .50,
                .75,
                .90,
                .95,
                .99
            ]
        )
        .to_string()
    )


# =====================================================================
# SAVE AUGMENTED JOINT TABLE
# =====================================================================

aug.to_csv(
    JOINT_OUT,
    index=False
)


print()
print("SAVED EVENT TABLE:")
print(EVENT_OUT)

print()
print("SAVED AUGMENTED JOINT TABLE:")
print(JOINT_OUT)

print()
print("=" * 112)
print("D09B COMPLETE")
print("=" * 112)
