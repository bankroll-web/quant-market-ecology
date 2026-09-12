import pandas as pd
import numpy as np
import pyarrow.parquet as pq
import pyarrow as pa
import zstandard as zstd
import io
import gc
from pathlib import Path

ROOT = Path(r"C:\Users\USER\Documents")
TRADE_DIR = ROOT / "CryptoHFT_Trades_8Hours"
REP_DIR = ROOT / "EXP01_REPLICATION"

HOURS = [
    "2026-05-25_04",
    "2026-05-25_12",
    "2026-05-25_18",
    "2026-05-26_15",
    "2026-05-26_21",
]

SUMMARY_FILE = REP_DIR / "gate3_d09_joint_tape_summary.csv"


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
        f"Unknown file signature: {sig!r}"
    )


def process_hour(hour):

    print()
    print("=" * 110)
    print(hour)
    print("=" * 110)

    trade_file = (
        TRADE_DIR
        / f"BTCUSDT_trades_{hour}.parquet"
    )

    book_file = (
        REP_DIR
        / f"{hour}_d07_liquidity_event_tape.csv"
    )

    out_file = (
        REP_DIR
        / f"{hour}_d09_joint_flow_liquidity_tape.csv"
    )

    trades = read_cryptohft(
        trade_file
    )

    book = pd.read_csv(
        book_file
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

    print(
        "RAW TRADES              :",
        f"{len(trades):,}"
    )

    print(
        "VALID BOOK EVENTS       :",
        f"{len(book):,}"
    )

    print(
        "VALID EPISODES          :",
        f"{book['episode_id'].nunique():,}"
    )

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

        if len(b) < 2:
            continue

        ep_start = int(
            b["event_time_ms"].iloc[0]
        )

        ep_end = int(
            b["event_time_ms"].iloc[-1]
        )

        et = trades[
            (
                trades["trade_time_ms"]
                >= ep_start
            )
            &
            (
                trades["trade_time_ms"]
                <= ep_end
            )
        ].sort_values(
            ["trade_time_ms", "trade_id"]
        )

        trade_times = (
            et["trade_time_ms"]
            .to_numpy(dtype=np.int64)
        )

        for i in range(
            1,
            len(b)
        ):

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

            # EXACT DISCOVERY CONVENTION:
            # (t0, t1]

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
                    n_trades
                    -
                    n_buy
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
                    buy_qty
                    -
                    sell_qty
                )

                total_flow = (
                    buy_qty
                    +
                    sell_qty
                )

                qty_sum = float(
                    ti["qty_num"].sum()
                )

                if qty_sum > 0:

                    trade_vwap = float(
                        (
                            ti["price_num"]
                            *
                            ti["qty_num"]
                        ).sum()
                        /
                        qty_sum
                    )

                else:

                    trade_vwap = np.nan

                exact_t1 = int(
                    (
                        ti["trade_time_ms"]
                        ==
                        t1
                    ).sum()
                )

                same_timestamp_trade_count += (
                    exact_t1
                )

                used_trade_count += (
                    n_trades
                )

            else:

                n_buy = 0
                n_sell = 0

                buy_qty = 0.0
                sell_qty = 0.0

                signed_flow = 0.0
                total_flow = 0.0

                trade_vwap = np.nan
                exact_t1 = 0

            # STARTING STATE = PREVIOUS EVENT AFTER-STATE

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
                ask0
                -
                bid0
            )

            bid_depth0 = float(
                prev["bid_depth5_after"]
            )

            ask_depth0 = float(
                prev["ask_depth5_after"]
            )

            depth_total0 = (
                bid_depth0
                +
                ask_depth0
            )

            if depth_total0 > 0:

                obi0 = (
                    bid_depth0
                    -
                    ask_depth0
                ) / depth_total0

            else:

                obi0 = np.nan

            mid1 = float(
                cur["mid_after"]
            )

            mid_change = (
                mid1
                -
                mid0
            )

            mid_change_bps = (
                10000.0
                *
                mid_change
                /
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

            eps = 1e-12

            buy_pressure = (
                buy_qty
                /
                (
                    ask_depth0
                    +
                    eps
                )
            )

            sell_pressure = (
                sell_qty
                /
                (
                    bid_depth0
                    +
                    eps
                )
            )

            net_pressure = (
                buy_pressure
                -
                sell_pressure
            )

            bid_net_response = (
                bid_add
                -
                bid_remove
            )

            ask_net_response = (
                ask_add
                -
                ask_remove
            )

            records.append({

                "hour":
                    hour,

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

                "buy_pressure":
                    buy_pressure,

                "sell_pressure":
                    sell_pressure,

                "net_pressure":
                    net_pressure,

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

                "mid_t1":
                    mid1,

                "mid_change":
                    mid_change,

                "mid_change_bps":
                    mid_change_bps,

                "mid_moved":
                    int(
                        mid_change != 0
                    ),

                "spread_t1":
                    float(
                        cur["spread_after"]
                    )
            })

    out = pd.DataFrame(
        records
    )

    if len(out):

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
            out_file,
            index=False
        )

    intervals_with_trade_rows = int(
        (
            out["n_trades"] > 0
        ).sum()
    )

    positive_flow_intervals = int(
        (
            out["total_flow_qty"] > 0
        ).sum()
    )

    exact_intervals = int(
        (
            out["trades_exactly_at_t1"] > 0
        ).sum()
    )

    episodes_with_intervals = int(
        out["episode_id"].nunique()
    )

    clean_intervals = int(
        (
            out["trades_exactly_at_t1"]
            ==
            0
        ).sum()
    )

    clean_flow = int(
        (
            (
                out["trades_exactly_at_t1"]
                ==
                0
            )
            &
            (
                out["total_flow_qty"]
                >
                0
            )
        ).sum()
    )

    print()
    print(
        "VALID L2 INTERVALS      :",
        f"{len(out):,}"
    )

    print(
        "EPISODES WITH INTERVALS :",
        f"{episodes_with_intervals:,}"
    )

    print(
        "INTERVALS WITH TRADES   :",
        f"{intervals_with_trade_rows:,}"
    )

    print(
        "POSITIVE-QTY FLOW INTV  :",
        f"{positive_flow_intervals:,}"
    )

    print(
        "TRADES ASSIGNED         :",
        f"{used_trade_count:,}"
    )

    print(
        "TRADES EXACTLY AT t1    :",
        f"{same_timestamp_trade_count:,}"
    )

    print(
        "INTERVALS WITH EXACT t1 :",
        f"{exact_intervals:,}"
    )

    print(
        "TIMESTAMP-CLEAN INTV    :",
        f"{clean_intervals:,}"
    )

    print(
        "CLEAN FLOW INTERVALS    :",
        f"{clean_flow:,}"
    )

    print()

    print(
        "INTERVAL MS MEAN        :",
        f"{out['interval_ms'].mean():.6f}"
    )

    print(
        "INTERVAL MS MEDIAN      :",
        f"{out['interval_ms'].median():.6f}"
    )

    print(
        "INTERVAL MS P99         :",
        f"{out['interval_ms'].quantile(.99):.6f}"
    )

    print(
        "INTERVAL MS MAX         :",
        f"{out['interval_ms'].max():.6f}"
    )

    print()

    print(
        "SAVED                   :",
        out_file
    )

    result = {

        "hour":
            hour,

        "valid_l2_intervals":
            len(out),

        "episodes_with_intervals":
            episodes_with_intervals,

        "intervals_with_trade_rows":
            intervals_with_trade_rows,

        "positive_qty_flow_intervals":
            positive_flow_intervals,

        "trades_assigned":
            used_trade_count,

        "trades_exactly_at_t1":
            same_timestamp_trade_count,

        "intervals_with_exact_t1":
            exact_intervals,

        "clean_intervals":
            clean_intervals,

        "clean_flow_intervals":
            clean_flow,

        "interval_ms_mean":
            float(
                out["interval_ms"].mean()
            ),

        "interval_ms_median":
            float(
                out["interval_ms"].median()
            ),

        "interval_ms_p99":
            float(
                out["interval_ms"].quantile(.99)
            ),

        "interval_ms_max":
            float(
                out["interval_ms"].max()
            ),

        "output_file":
            str(out_file)
    }

    del trades
    del book
    del out
    del records

    gc.collect()

    return result


print("=" * 110)
print("EXP-01 REPLICATION - CANONICAL D09")
print("JOINT FLOW -> LIQUIDITY INTERVAL TAPE")
print("=" * 110)

results = []

for hour in HOURS:

    try:

        results.append(
            process_hour(hour)
        )

    except Exception as exc:

        print()
        print(
            "ERROR:",
            hour,
            type(exc).__name__,
            str(exc)
        )

        results.append({
            "hour": hour,
            "error": (
                type(exc).__name__
                + ": "
                + str(exc)
            )
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
print("CANONICAL D09 SUMMARY")
print("=" * 110)

print(
    summary.to_string(
        index=False
    )
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
print("CANONICAL D09 COMPLETE")
print("=" * 110)
