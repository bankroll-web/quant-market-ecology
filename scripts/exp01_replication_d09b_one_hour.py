import sys
import gc
import io
from pathlib import Path

import numpy as np
import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq
import zstandard as zstd


ROOT = Path(r"C:\Users\USER\Documents")

RAW_DIR = (
    ROOT
    / "Audit_V2_1"
    / "Raw_Orderbooks"
)

REP_DIR = (
    ROOT
    / "EXP01_REPLICATION"
)


if len(sys.argv) != 2:

    raise SystemExit(
        "Usage: python exp01_replication_d09b_one_hour.py 2026-05-25_04"
    )


HOUR = sys.argv[1]


RAW_BOOK = (
    RAW_DIR
    / f"BTCUSDT_orderbook_{HOUR}.parquet"
)

D09_FILE = (
    REP_DIR
    / f"{HOUR}_d09_joint_flow_liquidity_tape.csv"
)

EVENT_OUT = (
    REP_DIR
    / f"{HOUR}_d09b_touch_distance_book_events.csv"
)

JOINT_OUT = (
    REP_DIR
    / f"{HOUR}_d09b_joint_flow_touch_ecology.csv"
)


print("=" * 112)
print("EXP-01 REPLICATION - CANONICAL D09B")
print("HOUR:", HOUR)
print("=" * 112)


def read_cryptohft(path):

    with open(path, "rb") as f:
        sig = f.read(4)

    if sig == b"PAR1":

        return pd.read_parquet(
            path
        )

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


# ======================================================================
# LOAD RAW BOOK
# ======================================================================

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


# ======================================================================
# EXACT DISCOVERY TICK INFERENCE
# ======================================================================

snap_sample = (
    df[
        df["event_type"]
        ==
        "snapshot"
    ]
    .head(1000)
)

sample_prices = np.sort(
    snap_sample[
        "price_num"
    ].unique()
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


# ======================================================================
# LOGICAL SNAPSHOT EVENTS
# ======================================================================

snap = df[
    df["event_type"]
    ==
    "snapshot"
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


# ======================================================================
# LOGICAL UPDATE EVENTS
# ======================================================================

upd = df[
    df["event_type"]
    ==
    "update"
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


events = (
    snapshots
    +
    updates
)

events.sort(
    key=lambda x: (
        x["received_time"],
        0
        if x["kind"] == "snapshot"
        else 1,
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


# ======================================================================
# BOOK STATE
# ======================================================================

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


def load_snapshot(rows):

    bids.clear()
    asks.clear()

    for r in rows.itertuples(
        index=False
    ):

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


def get_distance_bucket(
    side,
    price,
    best_bid,
    best_ask
):

    if side == "ask":

        raw_ticks = (
            price
            -
            best_ask
        ) / tick_size

    else:

        raw_ticks = (
            best_bid
            -
            price
        ) / tick_size


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
            new_q
            -
            old_q
        )


        ticks, bucket = (
            get_distance_bucket(
                side,
                p,
                best_bid_before,
                best_ask_before
            )
        )


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


        if delta > 0:

            ch[
                f"{side}_add_{bucket}_qty"
            ] += delta

            ch[
                f"{side}_add_{bucket}_levels"
            ] += 1


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


        if new_q == 0:

            book.pop(
                p,
                None
            )

        else:

            book[p] = new_q


    return ch


# ======================================================================
# CANONICAL D09B REPLAY
# ======================================================================

print()
print(
    "Beginning canonical D09B replay..."
)


for event in events:


    if event["kind"] == "snapshot":

        load_snapshot(
            event["rows"]
        )

        snapshot_last_id = int(
            event[
                "last_update_id"
            ]
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


    if waiting_bridge:

        if u <= snapshot_last_id:

            stale_skipped += 1

            continue


        target = (
            snapshot_last_id
            +
            1
        )


        if not (
            U
            <=
            target
            <=
            u
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


    best_bid_before = max(
        bids
    )

    best_ask_before = min(
        asks
    )

    mid_before = (
        best_bid_before
        +
        best_ask_before
    ) / 2.0


    changes = apply_and_classify(
        event["rows"],
        best_bid_before,
        best_ask_before
    )


    local_update_id = u


    if not bids or not asks:

        book_valid = False
        continue


    best_bid_after = max(
        bids
    )

    best_ask_after = min(
        asks
    )

    mid_after = (
        best_bid_after
        +
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
                event[
                    "transaction_time"
                ]
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
            mid_after
            -
            mid_before,

        **changes
    }


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


# ======================================================================
# DISTANCE TOTALS
# ======================================================================

print()
print(
    "DISPLAYED LIQUIDITY BY DISTANCE"
)


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
            add
            -
            remove
        )

        print(
            f"{side.upper():3s} "
            f"ADD={add:12.6f} "
            f"REMOVE={remove:12.6f} "
            f"NET={net:12.6f}"
        )


evt[
    "event_time_utc"
] = pd.to_datetime(
    evt[
        "event_time_ms"
    ],
    unit="ms",
    utc=True
)


evt.to_csv(
    EVENT_OUT,
    index=False
)


# ======================================================================
# MERGE WITH CANONICAL D09
# ======================================================================

joint = pd.read_csv(
    D09_FILE
)

joint[
    "episode_id"
] = pd.to_numeric(
    joint[
        "episode_id"
    ],
    errors="raise"
).astype("int64")


joint[
    "t1_event_time_ms"
] = pd.to_numeric(
    joint[
        "t1_event_time_ms"
    ],
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

    evt[
        touch_cols
    ],

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


match_rate = float(
    aug[
        "event_time_ms"
    ]
    .notna()
    .mean()
)


clean = aug[
    aug[
        "trades_exactly_at_t1"
    ]
    ==
    0
].copy()


flow_clean = clean[
    clean[
        "total_flow_qty"
    ]
    >
    0
].copy()


signed_clean = flow_clean[
    flow_clean[
        "signed_flow_qty"
    ]
    !=
    0
].copy()


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


print()
print(
    "ALL INTERVALS         :",
    f"{len(aug):,}"
)

print(
    "CLEAN INTERVALS       :",
    f"{len(clean):,}"
)

print(
    "REMOVED EXACT-t1      :",
    f"{len(aug) - len(clean):,}"
)

print(
    "CLEAN FLOW INTERVALS  :",
    f"{len(flow_clean):,}"
)

print(
    "NONZERO SIGNED FLOW   :",
    f"{len(signed_clean):,}"
)


if len(flow_clean):

    print()
    print(
        "NEAR-TOUCH FLOW-INTERVAL SUMMARY"
    )

    cols = [
        "bid_add_0_5_qty",
        "bid_remove_0_5_qty",
        "bid_net_0_5_qty",
        "ask_add_0_5_qty",
        "ask_remove_0_5_qty",
        "ask_net_0_5_qty"
    ]

    print(
        flow_clean[
            cols
        ]
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


aug.to_csv(
    JOINT_OUT,
    index=False
)


gate_pass = bool(

    valid_bridges > 0

    and
    sequence_failures == 0

    and
    len(evt) > 0

    and
    len(aug) == len(joint)

    and
    match_rate == 1.0
)


print()
print(
    "CANONICAL D09B GATE   :",
    "PASS"
    if gate_pass
    else
    "FAIL"
)

print()
print(
    "SAVED EVENT TABLE:"
)

print(
    EVENT_OUT
)

print()
print(
    "SAVED JOINT TABLE:"
)

print(
    JOINT_OUT
)

print()
print("=" * 112)
print("D09B COMPLETE")
print("=" * 112)


del df
del evt
del joint
del aug
del clean
del flow_clean
del signed_clean
del records
del events

gc.collect()
