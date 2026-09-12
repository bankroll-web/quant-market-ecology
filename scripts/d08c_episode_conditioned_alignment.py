import pandas as pd
import pyarrow.parquet as pq
import pyarrow as pa
import zstandard as zstd
import io
import numpy as np
from pathlib import Path

TRADE_FILE = Path(
    r"C:\Users\USER\Documents\CryptoHFT_Trades_8Hours"
    r"\BTCUSDT_trades_2026-05-25_00.parquet"
)

BOOK_FILE = Path(
    r"C:\Users\USER\Documents\d07_liquidity_event_tape.csv"
)

OUT_FILE = Path(
    r"C:\Users\USER\Documents\d08c_episode_conditioned_alignment.csv"
)

print("=" * 108)
print("CRYPTOHFT D08C - VERIFIED-EPISODE TRADE / L2 ALIGNMENT")
print("=" * 108)


# ====================================================================
# READ CRYPTOHFT FILE
# ====================================================================

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


# ====================================================================
# LOAD
# ====================================================================

trades = read_cryptohft(
    TRADE_FILE
)

book = pd.read_csv(
    BOOK_FILE
)

trades["trade_time_ms"] = pd.to_numeric(
    trades["trade_time"],
    errors="raise"
).astype("int64")

trades["price_num"] = pd.to_numeric(
    trades["price"],
    errors="raise"
)

trades["qty_num"] = pd.to_numeric(
    trades["quantity"],
    errors="raise"
)

trades["aggressor_side"] = np.where(
    trades["is_buyer_maker"],
    "SELL",
    "BUY"
)

book["event_time_ms"] = pd.to_numeric(
    book["event_time_ms"],
    errors="raise"
).astype("int64")

book["transaction_time_ms"] = pd.to_numeric(
    book["transaction_time_ms"],
    errors="raise"
).astype("int64")

book["episode_id"] = pd.to_numeric(
    book["episode_id"],
    errors="raise"
).astype("int64")


print()
print("TRADES:", f"{len(trades):,}")
print("VALID L2 EVENTS:", f"{len(book):,}")
print(
    "VALID EPISODES:",
    f"{book['episode_id'].nunique():,}"
)


# ====================================================================
# EPISODE BOUNDS
# ====================================================================

episodes = (
    book.groupby("episode_id")
    .agg(
        start_ms=("event_time_ms", "min"),
        end_ms=("event_time_ms", "max"),
        n_book_events=("event_time_ms", "size")
    )
    .reset_index()
    .sort_values("start_ms")
)

episodes["duration_ms"] = (
    episodes["end_ms"]
    -
    episodes["start_ms"]
)


print()
print("=" * 108)
print("EPISODE STRUCTURE")
print("=" * 108)

print(
    episodes[
        [
            "duration_ms",
            "n_book_events"
        ]
    ].describe(
        percentiles=[
            .25, .50, .75, .90, .95, .99
        ]
    ).to_string()
)


# ====================================================================
# ALIGN TRADES INSIDE EACH VERIFIED EPISODE
# ====================================================================

records = []

for ep in episodes.itertuples(index=False):

    ep_id = int(ep.episode_id)

    b = (
        book[
            book["episode_id"] == ep_id
        ]
        .sort_values("event_time_ms")
        .reset_index(drop=True)
    )

    times = (
        b["event_time_ms"]
        .to_numpy(dtype=np.int64)
    )

    # Strictly keep trades inside valid reconstructed interval.

    t = trades[
        (trades["trade_time_ms"] >= int(ep.start_ms))
        &
        (trades["trade_time_ms"] <= int(ep.end_ms))
    ].copy()

    if len(t) == 0:
        continue

    for tr in t.itertuples(index=False):

        tt = int(tr.trade_time_ms)

        pos = int(
            np.searchsorted(
                times,
                tt,
                side="left"
            )
        )

        # Previous event

        if pos < len(times) and times[pos] == tt:
            prev_idx = pos
            next_idx = pos

        else:
            prev_idx = pos - 1
            next_idx = pos

        prev_time = (
            int(times[prev_idx])
            if prev_idx >= 0
            else None
        )

        next_time = (
            int(times[next_idx])
            if next_idx < len(times)
            else None
        )

        prev_lag = (
            tt - prev_time
            if prev_time is not None
            else np.nan
        )

        next_lead = (
            next_time - tt
            if next_time is not None
            else np.nan
        )

        candidates = []

        if prev_time is not None:
            candidates.append(
                (
                    abs(tt - prev_time),
                    prev_idx
                )
            )

        if next_time is not None:
            candidates.append(
                (
                    abs(next_time - tt),
                    next_idx
                )
            )

        if not candidates:
            continue

        nearest_distance, near_idx = min(
            candidates,
            key=lambda x: x[0]
        )

        near_row = b.iloc[near_idx]

        records.append({

            "episode_id": ep_id,

            "trade_id":
                int(tr.trade_id),

            "trade_time_ms":
                tt,

            "trade_price":
                float(tr.price_num),

            "trade_qty":
                float(tr.qty_num),

            "aggressor_side":
                tr.aggressor_side,

            "prev_book_time_ms":
                prev_time,

            "next_book_time_ms":
                next_time,

            "previous_lag_ms":
                prev_lag,

            "next_lead_ms":
                next_lead,

            "nearest_distance_ms":
                nearest_distance,

            "nearest_book_time_ms":
                int(
                    near_row["event_time_ms"]
                ),

            "mid_before":
                float(
                    near_row["mid_before"]
                ),

            "mid_after":
                float(
                    near_row["mid_after"]
                ),

            "best_bid_before":
                float(
                    near_row["best_bid_before"]
                ),

            "best_ask_before":
                float(
                    near_row["best_ask_before"]
                ),

            "bid_depth5_before":
                float(
                    near_row["bid_depth5_before"]
                ),

            "ask_depth5_before":
                float(
                    near_row["ask_depth5_before"]
                ),

            "bid_add_qty":
                float(
                    near_row["bid_add_qty"]
                ),

            "ask_add_qty":
                float(
                    near_row["ask_add_qty"]
                ),

            "bid_remove_qty":
                float(
                    near_row["bid_remove_qty"]
                ),

            "ask_remove_qty":
                float(
                    near_row["ask_remove_qty"]
                )
        })


out = pd.DataFrame(records)


# ====================================================================
# RESULTS
# ====================================================================

print()
print("=" * 108)
print("EPISODE-CONDITIONED TRADE COVERAGE")
print("=" * 108)

print(
    "TOTAL RAW TRADES:",
    f"{len(trades):,}"
)

print(
    "TRADES INSIDE VERIFIED EPISODES:",
    f"{len(out):,}"
)

print(
    "SHARE OF ALL TRADES:",
    f"{len(out) / len(trades):.6f}"
)


if len(out):

    print()
    print("=" * 108)
    print("NEAREST L2 DISTANCE INSIDE VERIFIED EPISODES")
    print("=" * 108)

    print(
        out["nearest_distance_ms"]
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


    print()
    print("=" * 108)
    print("ALIGNMENT COVERAGE")
    print("=" * 108)

    for window in [
        0,
        1,
        5,
        10,
        15,
        20,
        25,
        30,
        40,
        50,
        75,
        100,
        250,
        500,
        1000
    ]:

        n = int(
            (
                out["nearest_distance_ms"]
                <= window
            ).sum()
        )

        pct = (
            n / len(out)
        )

        print(
            f"WITHIN {window:4d} ms : "
            f"{n:8,d}  "
            f"{pct:10.6f}"
        )


    print()
    print("=" * 108)
    print("PREVIOUS / NEXT BOOK TIMING")
    print("=" * 108)

    print()
    print("PREVIOUS LAG")

    print(
        out["previous_lag_ms"]
        .dropna()
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

    print()
    print("NEXT LEAD")

    print(
        out["next_lead_ms"]
        .dropna()
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


    # ================================================================
    # TRADE PRICE VS NEAREST PRE-EVENT TOUCH
    # ================================================================

    buy = out[
        out["aggressor_side"] == "BUY"
    ]

    sell = out[
        out["aggressor_side"] == "SELL"
    ]

    buy_touch = (
        buy["trade_price"]
        >=
        buy["best_ask_before"]
    )

    sell_touch = (
        sell["trade_price"]
        <=
        sell["best_bid_before"]
    )

    print()
    print("=" * 108)
    print("TRADE / TOUCH SANITY INSIDE VERIFIED EPISODES")
    print("=" * 108)

    print(
        "BUY TRADES:",
        f"{len(buy):,}"
    )

    print(
        "SELL TRADES:",
        f"{len(sell):,}"
    )

    print(
        "BUY >= BOOK ASK:",
        f"{int(buy_touch.sum()):,}",
        f"({buy_touch.mean():.6f})"
    )

    print(
        "SELL <= BOOK BID:",
        f"{int(sell_touch.sum()):,}",
        f"({sell_touch.mean():.6f})"
    )


    # ================================================================
    # FLOW
    # ================================================================

    print()
    print("=" * 108)
    print("VERIFIED-EPISODE FLOW")
    print("=" * 108)

    print(
        "BUY QTY:",
        round(
            buy["trade_qty"].sum(),
            6
        )
    )

    print(
        "SELL QTY:",
        round(
            sell["trade_qty"].sum(),
            6
        )
    )


    out["trade_time_utc"] = pd.to_datetime(
        out["trade_time_ms"],
        unit="ms",
        utc=True
    )

    out.to_csv(
        OUT_FILE,
        index=False
    )

    print()
    print("SAVED:")
    print(OUT_FILE)


print()
print("=" * 108)
print("D08C COMPLETE")
print("=" * 108)
