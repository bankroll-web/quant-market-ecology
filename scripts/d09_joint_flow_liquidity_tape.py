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
    r"C:\Users\USER\Documents\d09_joint_flow_liquidity_tape.csv"
)

print("=" * 110)
print("CRYPTOHFT D09 - JOINT FLOW -> LIQUIDITY RESPONSE TAPE")
print("=" * 110)


# =====================================================================
# READ OUTER-ZSTD PARQUET
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
            raise RuntimeError("Inner payload is not Parquet")

        return pq.read_table(
            pa.BufferReader(raw)
        ).to_pandas()

    raise RuntimeError(
        f"Unknown file signature: {sig!r}"
    )


# =====================================================================
# LOAD
# =====================================================================

trades = read_cryptohft(TRADE_FILE)
book = pd.read_csv(BOOK_FILE)

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

trades["is_buy"] = (
    ~trades["is_buyer_maker"]
)

trades["signed_qty"] = np.where(
    trades["is_buy"],
    trades["qty_num"],
    -trades["qty_num"]
)

book["event_time_ms"] = pd.to_numeric(
    book["event_time_ms"],
    errors="raise"
).astype("int64")

book["episode_id"] = pd.to_numeric(
    book["episode_id"],
    errors="raise"
).astype("int64")

book = book.sort_values(
    ["episode_id", "event_time_ms"]
).reset_index(drop=True)


print()
print("RAW TRADES       :", f"{len(trades):,}")
print("VALID BOOK EVENTS:", f"{len(book):,}")
print(
    "VALID EPISODES   :",
    f"{book['episode_id'].nunique():,}"
)


# =====================================================================
# BUILD CONSECUTIVE VALID L2 INTERVALS
# =====================================================================

records = []

same_timestamp_trade_count = 0
used_trade_count = 0

for ep_id, b in book.groupby(
    "episode_id",
    sort=True
):

    b = (
        b.sort_values("event_time_ms")
        .reset_index(drop=True)
    )

    # Need at least two events to construct one interval.
    if len(b) < 2:
        continue

    ep_start = int(
        b["event_time_ms"].iloc[0]
    )

    ep_end = int(
        b["event_time_ms"].iloc[-1]
    )

    et = trades[
        (trades["trade_time_ms"] >= ep_start)
        &
        (trades["trade_time_ms"] <= ep_end)
    ].sort_values(
        ["trade_time_ms", "trade_id"]
    )

    trade_times = et[
        "trade_time_ms"
    ].to_numpy(dtype=np.int64)

    for i in range(1, len(b)):

        prev = b.iloc[i - 1]
        cur = b.iloc[i]

        t0 = int(
            prev["event_time_ms"]
        )

        t1 = int(
            cur["event_time_ms"]
        )

        if t1 <= t0:
            continue

        # -------------------------------------------------------------
        # Primary convention:
        #
        # trades strictly AFTER previous L2 event
        # and up to/current L2 event:
        #
        # (t0, t1]
        #
        # Trades sharing t1 exactly are retained but separately counted
        # because ordering inside the exact millisecond is ambiguous.
        # -------------------------------------------------------------

        left = np.searchsorted(
            trade_times,
            t0,
            side="right"
        )

        right = np.searchsorted(
            trade_times,
            t1,
            side="right"
        )

        ti = et.iloc[
            left:right
        ]

        n_trades = len(ti)

        if n_trades:

            n_buy = int(
                ti["is_buy"].sum()
            )

            n_sell = (
                n_trades - n_buy
            )

            buy_qty = float(
                ti.loc[
                    ti["is_buy"],
                    "qty_num"
                ].sum()
            )

            sell_qty = float(
                ti.loc[
                    ~ti["is_buy"],
                    "qty_num"
                ].sum()
            )

            signed_flow = (
                buy_qty - sell_qty
            )

            total_flow = (
                buy_qty + sell_qty
            )

            trade_vwap = float(
                (
                    ti["price_num"]
                    *
                    ti["qty_num"]
                ).sum()
                /
                ti["qty_num"].sum()
            )

            exact_t1 = int(
                (
                    ti["trade_time_ms"]
                    == t1
                ).sum()
            )

            same_timestamp_trade_count += exact_t1
            used_trade_count += n_trades

        else:

            n_buy = 0
            n_sell = 0

            buy_qty = 0.0
            sell_qty = 0.0

            signed_flow = 0.0
            total_flow = 0.0

            trade_vwap = np.nan
            exact_t1 = 0


        # -------------------------------------------------------------
        # STATE BEFORE INTERVAL
        #
        # prev row's AFTER-state is the known book state entering
        # the interval.
        # -------------------------------------------------------------

        bid0 = float(
            prev["best_bid_after"]
        )

        ask0 = float(
            prev["best_ask_after"]
        )

        mid0 = float(
            prev["mid_after"]
        )

        spread0 = (
            ask0 - bid0
        )

        bid_depth0 = float(
            prev["bid_depth5_after"]
        )

        ask_depth0 = float(
            prev["ask_depth5_after"]
        )

        depth_total0 = (
            bid_depth0 +
            ask_depth0
        )

        if depth_total0 > 0:

            obi0 = (
                bid_depth0 -
                ask_depth0
            ) / depth_total0

        else:

            obi0 = np.nan


        # -------------------------------------------------------------
        # CURRENT BOOK RESPONSE
        # -------------------------------------------------------------

        mid1 = float(
            cur["mid_after"]
        )

        mid_change = (
            mid1 - mid0
        )

        mid_change_bps = (
            10000.0 *
            mid_change /
            mid0
        )

        bid_add = float(
            cur["bid_add_qty"]
        )

        ask_add = float(
            cur["ask_add_qty"]
        )

        bid_remove = float(
            cur["bid_remove_qty"]
        )

        ask_remove = float(
            cur["ask_remove_qty"]
        )


        # -------------------------------------------------------------
        # FLOW PRESSURE
        #
        # These are descriptive state variables, NOT trading signals.
        # -------------------------------------------------------------

        eps = 1e-12

        buy_pressure = (
            buy_qty /
            (ask_depth0 + eps)
        )

        sell_pressure = (
            sell_qty /
            (bid_depth0 + eps)
        )

        net_pressure = (
            buy_pressure -
            sell_pressure
        )


        # -------------------------------------------------------------
        # SIMPLE LIQUIDITY RESPONSE COORDINATES
        #
        # Positive ask net response = more ask liquidity added than
        # removed at the response update.
        #
        # Positive bid net response = more bid liquidity added than
        # removed.
        # -------------------------------------------------------------

        ask_net_response = (
            ask_add -
            ask_remove
        )

        bid_net_response = (
            bid_add -
            bid_remove
        )


        records.append({

            "episode_id":
                int(ep_id),

            "interval_index":
                i,

            "t0_event_time_ms":
                t0,

            "t1_event_time_ms":
                t1,

            "interval_ms":
                t1 - t0,

            # initial state

            "mid_t0":
                mid0,

            "best_bid_t0":
                bid0,

            "best_ask_t0":
                ask0,

            "spread_t0":
                spread0,

            "bid_depth5_t0":
                bid_depth0,

            "ask_depth5_t0":
                ask_depth0,

            "obi5_t0":
                obi0,

            # flow

            "n_trades":
                n_trades,

            "n_buy_trades":
                n_buy,

            "n_sell_trades":
                n_sell,

            "aggressive_buy_qty":
                buy_qty,

            "aggressive_sell_qty":
                sell_qty,

            "signed_flow_qty":
                signed_flow,

            "total_flow_qty":
                total_flow,

            "trade_vwap":
                trade_vwap,

            "trades_exactly_at_t1":
                exact_t1,

            # normalized pressure

            "buy_pressure":
                buy_pressure,

            "sell_pressure":
                sell_pressure,

            "net_pressure":
                net_pressure,

            # response event

            "bid_add_qty":
                bid_add,

            "ask_add_qty":
                ask_add,

            "bid_remove_qty":
                bid_remove,

            "ask_remove_qty":
                ask_remove,

            "bid_net_response":
                bid_net_response,

            "ask_net_response":
                ask_net_response,

            "total_add_qty":
                float(
                    cur["total_add_qty"]
                ),

            "total_remove_qty":
                float(
                    cur["total_remove_qty"]
                ),

            # price response

            "mid_t1":
                mid1,

            "mid_change":
                mid_change,

            "mid_change_bps":
                mid_change_bps,

            "mid_moved":
                int(mid_change != 0),

            "spread_t1":
                float(
                    cur["spread_after"]
                )
        })


# =====================================================================
# OUTPUT
# =====================================================================

out = pd.DataFrame(records)

print()
print("=" * 110)
print("D09 JOINT-TAPE RESULTS")
print("=" * 110)

print(
    "VALID L2 INTERVALS     :",
    f"{len(out):,}"
)

if len(out):

    print(
        "EPISODES WITH INTERVALS:",
        f"{out['episode_id'].nunique():,}"
    )

    print(
        "INTERVALS WITH TRADES  :",
        f"{int((out['n_trades'] > 0).sum()):,}"
    )

    print(
        "SHARE WITH TRADES      :",
        f"{(out['n_trades'] > 0).mean():.6f}"
    )

    print(
        "TRADES ASSIGNED        :",
        f"{used_trade_count:,}"
    )

    print(
        "TRADES EXACTLY AT t1   :",
        f"{same_timestamp_trade_count:,}"
    )

    print()
    print("INTERVAL LENGTH (ms)")

    print(
        out["interval_ms"]
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
    print("TRADES PER L2 INTERVAL")

    print(
        out["n_trades"]
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
    print("AGGRESSIVE FLOW QTY")

    print(
        out[
            [
                "aggressive_buy_qty",
                "aggressive_sell_qty",
                "signed_flow_qty",
                "total_flow_qty"
            ]
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


    print()
    print("FLOW PRESSURE")

    print(
        out[
            [
                "buy_pressure",
                "sell_pressure",
                "net_pressure"
            ]
        ]
        .replace(
            [np.inf, -np.inf],
            np.nan
        )
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
    print("BOOK RESPONSE")

    print(
        out[
            [
                "bid_add_qty",
                "ask_add_qty",
                "bid_remove_qty",
                "ask_remove_qty",
                "bid_net_response",
                "ask_net_response"
            ]
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


    print()
    print("MIDPRICE RESPONSE")

    print(
        out["mid_change_bps"]
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

    print(
        "MID-MOVING INTERVALS   :",
        f"{int(out['mid_moved'].sum()):,}"
    )

    print(
        "MID-MOVE RATE          :",
        f"{out['mid_moved'].mean():.6f}"
    )


    # ---------------------------------------------------------------
    # Conditional descriptive comparison.
    # Not a prediction test.
    # ---------------------------------------------------------------

    has_flow = out[
        out["total_flow_qty"] > 0
    ].copy()

    no_flow = out[
        out["total_flow_qty"] == 0
    ].copy()

    print()
    print("=" * 110)
    print("DESCRIPTIVE FLOW / NO-FLOW COMPARISON")
    print("=" * 110)

    print(
        "FLOW INTERVALS:",
        f"{len(has_flow):,}"
    )

    print(
        "NO-FLOW INTERVALS:",
        f"{len(no_flow):,}"
    )

    if len(has_flow):

        print(
            "FLOW MID-MOVE RATE:",
            f"{has_flow['mid_moved'].mean():.6f}"
        )

        print(
            "FLOW MEAN ABS MID MOVE BPS:",
            f"{has_flow['mid_change_bps'].abs().mean():.6f}"
        )

    if len(no_flow):

        print(
            "NO-FLOW MID-MOVE RATE:",
            f"{no_flow['mid_moved'].mean():.6f}"
        )

        print(
            "NO-FLOW MEAN ABS MID MOVE BPS:",
            f"{no_flow['mid_change_bps'].abs().mean():.6f}"
        )


    out["t0_utc"] = pd.to_datetime(
        out["t0_event_time_ms"],
        unit="ms",
        utc=True
    )

    out["t1_utc"] = pd.to_datetime(
        out["t1_event_time_ms"],
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
print("=" * 110)
print("D09 COMPLETE")
print("=" * 110)
