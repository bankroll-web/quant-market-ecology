import pandas as pd
import pyarrow.parquet as pq
import pyarrow as pa
import zstandard as zstd
import io
import numpy as np
from pathlib import Path


ROOT = Path(r"C:\Users\USER\Documents")

TRADE_DIR = (
    ROOT
    / "CryptoHFT_Trades_8Hours"
)

REP_DIR = (
    ROOT
    / "EXP01_REPLICATION"
)

SUMMARY_FILE = (
    REP_DIR
    / "gate2_d08c_alignment_summary.csv"
)


HOURS = [
    "2026-05-25_04",
    "2026-05-25_12",
    "2026-05-25_18",
    "2026-05-26_15",
    "2026-05-26_21",
]


print("=" * 112)
print("EXP-01 INDEPENDENT REPLICATION")
print("GATE 2 - CANONICAL D08C VERIFIED-EPISODE TRADE / L2 ALIGNMENT")
print("=" * 112)


# ======================================================================
# CRYPTOHFT READER
# ======================================================================

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
# PROCESS ONE HOUR
# ======================================================================

def process_hour(hour):

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
        / f"{hour}_d08c_episode_alignment.csv"
    )


    print()
    print("=" * 112)
    print(hour)
    print("=" * 112)


    # ------------------------------------------------------------------
    # LOAD
    # ------------------------------------------------------------------

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


    print(
        "RAW TRADES              :",
        f"{len(trades):,}"
    )

    print(
        "VALID L2 EVENTS         :",
        f"{len(book):,}"
    )

    print(
        "VALID EPISODES          :",
        f"{book['episode_id'].nunique():,}"
    )


    # ------------------------------------------------------------------
    # SORT TRADES ONCE
    #
    # This is only a computational optimization.
    # Episode membership definition remains:
    #
    # start_ms <= trade_time <= end_ms
    # ------------------------------------------------------------------

    trades = (
        trades
        .sort_values("trade_time_ms")
        .reset_index(drop=True)
    )

    trade_times = (
        trades["trade_time_ms"]
        .to_numpy(dtype=np.int64)
    )


    # ------------------------------------------------------------------
    # EPISODE BOUNDS
    # ------------------------------------------------------------------

    episodes = (
        book.groupby("episode_id")
        .agg(
            start_ms=(
                "event_time_ms",
                "min"
            ),
            end_ms=(
                "event_time_ms",
                "max"
            ),
            n_book_events=(
                "event_time_ms",
                "size"
            )
        )
        .reset_index()
        .sort_values("start_ms")
    )


    episodes["duration_ms"] = (
        episodes["end_ms"]
        -
        episodes["start_ms"]
    )


    records = []


    # ==================================================================
    # EXACT D08C EPISODE-CONDITIONED ALIGNMENT
    # ==================================================================

    for ep in episodes.itertuples(
        index=False
    ):

        ep_id = int(
            ep.episode_id
        )

        b = (
            book[
                book["episode_id"]
                ==
                ep_id
            ]
            .sort_values(
                "event_time_ms"
            )
            .reset_index(
                drop=True
            )
        )


        times = (
            b["event_time_ms"]
            .to_numpy(
                dtype=np.int64
            )
        )


        # --------------------------------------------------------------
        # Efficient equivalent of:
        #
        # trades[
        #   trade_time >= start_ms
        #   &
        #   trade_time <= end_ms
        # ]
        #
        # Inclusive on both ends, exactly as D08C.
        # --------------------------------------------------------------

        lo = int(
            np.searchsorted(
                trade_times,
                int(ep.start_ms),
                side="left"
            )
        )

        hi = int(
            np.searchsorted(
                trade_times,
                int(ep.end_ms),
                side="right"
            )
        )


        if hi <= lo:
            continue


        t = trades.iloc[
            lo:hi
        ]


        for tr in t.itertuples(
            index=False
        ):

            tt = int(
                tr.trade_time_ms
            )


            pos = int(
                np.searchsorted(
                    times,
                    tt,
                    side="left"
                )
            )


            # ----------------------------------------------------------
            # SAME D08C EQUALITY RULE
            # ----------------------------------------------------------

            if (
                pos < len(times)
                and
                times[pos] == tt
            ):

                prev_idx = pos
                next_idx = pos

            else:

                prev_idx = (
                    pos - 1
                )

                next_idx = pos


            prev_time = (
                int(
                    times[
                        prev_idx
                    ]
                )
                if prev_idx >= 0
                else None
            )


            next_time = (
                int(
                    times[
                        next_idx
                    ]
                )
                if next_idx < len(times)
                else None
            )


            prev_lag = (
                tt
                -
                prev_time
                if prev_time is not None
                else np.nan
            )


            next_lead = (
                next_time
                -
                tt
                if next_time is not None
                else np.nan
            )


            candidates = []


            if prev_time is not None:

                candidates.append(
                    (
                        abs(
                            tt
                            -
                            prev_time
                        ),
                        prev_idx
                    )
                )


            if next_time is not None:

                candidates.append(
                    (
                        abs(
                            next_time
                            -
                            tt
                        ),
                        next_idx
                    )
                )


            if not candidates:
                continue


            nearest_distance, near_idx = min(
                candidates,
                key=lambda x: x[0]
            )


            near_row = b.iloc[
                near_idx
            ]


            records.append({

                "hour":
                    hour,

                "episode_id":
                    ep_id,

                "trade_id":
                    int(
                        tr.trade_id
                    ),

                "trade_time_ms":
                    tt,

                "trade_price":
                    float(
                        tr.price_num
                    ),

                "trade_qty":
                    float(
                        tr.qty_num
                    ),

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
                    int(
                        nearest_distance
                    ),

                "nearest_book_time_ms":
                    int(
                        near_row[
                            "event_time_ms"
                        ]
                    ),

                "mid_before":
                    float(
                        near_row[
                            "mid_before"
                        ]
                    ),

                "mid_after":
                    float(
                        near_row[
                            "mid_after"
                        ]
                    ),

                "best_bid_before":
                    float(
                        near_row[
                            "best_bid_before"
                        ]
                    ),

                "best_ask_before":
                    float(
                        near_row[
                            "best_ask_before"
                        ]
                    ),

                "bid_depth5_before":
                    float(
                        near_row[
                            "bid_depth5_before"
                        ]
                    ),

                "ask_depth5_before":
                    float(
                        near_row[
                            "ask_depth5_before"
                        ]
                    ),

                "bid_add_qty":
                    float(
                        near_row[
                            "bid_add_qty"
                        ]
                    ),

                "ask_add_qty":
                    float(
                        near_row[
                            "ask_add_qty"
                        ]
                    ),

                "bid_remove_qty":
                    float(
                        near_row[
                            "bid_remove_qty"
                        ]
                    ),

                "ask_remove_qty":
                    float(
                        near_row[
                            "ask_remove_qty"
                        ]
                    )
            })


    out = pd.DataFrame(
        records
    )


    # ==================================================================
    # AUDITS
    # ==================================================================

    if len(out) == 0:

        print(
            "NO ALIGNED TRADES."
        )

        return {

            "hour":
                hour,

            "gate2_pass":
                False,

            "reason":
                "No aligned trades"
        }


    # ------------------------------------------------------------------
    # DUPLICATE TRADE AUDIT
    # ------------------------------------------------------------------

    duplicate_trade_ids = int(
        out["trade_id"]
        .duplicated()
        .sum()
    )


    # ------------------------------------------------------------------
    # TIMING AUDIT
    # ------------------------------------------------------------------

    negative_prev = int(
        (
            out[
                "previous_lag_ms"
            ]
            .dropna()
            <
            0
        ).sum()
    )


    negative_next = int(
        (
            out[
                "next_lead_ms"
            ]
            .dropna()
            <
            0
        ).sum()
    )


    within_10 = float(
        (
            out[
                "nearest_distance_ms"
            ]
            <=
            10
        ).mean()
    )


    within_15 = float(
        (
            out[
                "nearest_distance_ms"
            ]
            <=
            15
        ).mean()
    )


    within_25 = float(
        (
            out[
                "nearest_distance_ms"
            ]
            <=
            25
        ).mean()
    )


    within_50 = float(
        (
            out[
                "nearest_distance_ms"
            ]
            <=
            50
        ).mean()
    )


    nearest_mean = float(
        out[
            "nearest_distance_ms"
        ].mean()
    )


    nearest_median = float(
        out[
            "nearest_distance_ms"
        ].median()
    )


    nearest_p95 = float(
        out[
            "nearest_distance_ms"
        ].quantile(
            0.95
        )
    )


    nearest_p99 = float(
        out[
            "nearest_distance_ms"
        ].quantile(
            0.99
        )
    )


    nearest_max = float(
        out[
            "nearest_distance_ms"
        ].max()
    )


    # ------------------------------------------------------------------
    # TOUCH SANITY
    # ------------------------------------------------------------------

    buy = out[
        out[
            "aggressor_side"
        ]
        ==
        "BUY"
    ]


    sell = out[
        out[
            "aggressor_side"
        ]
        ==
        "SELL"
    ]


    buy_touch = (
        buy[
            "trade_price"
        ]
        >=
        buy[
            "best_ask_before"
        ]
    )


    sell_touch = (
        sell[
            "trade_price"
        ]
        <=
        sell[
            "best_bid_before"
        ]
    )


    buy_touch_rate = (
        float(
            buy_touch.mean()
        )
        if len(buy)
        else np.nan
    )


    sell_touch_rate = (
        float(
            sell_touch.mean()
        )
        if len(sell)
        else np.nan
    )


    coverage = (
        len(out)
        /
        len(trades)
    )


    # ------------------------------------------------------------------
    # PRE-FROZEN TECHNICAL GATE
    # ------------------------------------------------------------------

    gate2_pass = bool(

        len(out) > 0

        and
        duplicate_trade_ids == 0

        and
        negative_prev == 0

        and
        negative_next == 0

        and
        within_50 >= 0.99

        and
        buy_touch_rate >= 0.95

        and
        sell_touch_rate >= 0.95
    )


    # ------------------------------------------------------------------
    # SAVE
    # ------------------------------------------------------------------

    out[
        "trade_time_utc"
    ] = pd.to_datetime(
        out[
            "trade_time_ms"
        ],
        unit="ms",
        utc=True
    )


    out.to_csv(
        out_file,
        index=False
    )


    # ------------------------------------------------------------------
    # PRINT
    # ------------------------------------------------------------------

    print()
    print(
        "TRADES INSIDE VERIFIED EPISODES :",
        f"{len(out):,}"
    )

    print(
        "SHARE OF RAW TRADES              :",
        f"{coverage:.6f}"
    )

    print()


    print(
        "DUPLICATE TRADE IDS              :",
        f"{duplicate_trade_ids:,}"
    )

    print(
        "NEGATIVE PREVIOUS LAGS           :",
        f"{negative_prev:,}"
    )

    print(
        "NEGATIVE NEXT LEADS              :",
        f"{negative_next:,}"
    )

    print()


    print(
        "NEAREST DISTANCE MEAN MS         :",
        f"{nearest_mean:.6f}"
    )

    print(
        "NEAREST DISTANCE MEDIAN MS       :",
        f"{nearest_median:.6f}"
    )

    print(
        "NEAREST DISTANCE P95 MS          :",
        f"{nearest_p95:.6f}"
    )

    print(
        "NEAREST DISTANCE P99 MS          :",
        f"{nearest_p99:.6f}"
    )

    print(
        "NEAREST DISTANCE MAX MS          :",
        f"{nearest_max:.6f}"
    )

    print()


    print(
        "WITHIN 10 MS                     :",
        f"{within_10:.6f}"
    )

    print(
        "WITHIN 15 MS                     :",
        f"{within_15:.6f}"
    )

    print(
        "WITHIN 25 MS                     :",
        f"{within_25:.6f}"
    )

    print(
        "WITHIN 50 MS                     :",
        f"{within_50:.6f}"
    )

    print()


    print(
        "BUY TRADES                       :",
        f"{len(buy):,}"
    )

    print(
        "BUY >= PRE-EVENT ASK             :",
        f"{buy_touch_rate:.6f}"
    )

    print(
        "SELL TRADES                      :",
        f"{len(sell):,}"
    )

    print(
        "SELL <= PRE-EVENT BID            :",
        f"{sell_touch_rate:.6f}"
    )

    print()


    print(
        "CANONICAL GATE 2                 :",
        "PASS"
        if gate2_pass
        else
        "FAIL"
    )

    print(
        "SAVED                            :",
        out_file
    )


    return {

        "hour":
            hour,

        "raw_trades":
            len(trades),

        "aligned_trades":
            len(out),

        "trade_coverage":
            coverage,

        "episodes":
            int(
                book[
                    "episode_id"
                ].nunique()
            ),

        "duplicate_trade_ids":
            duplicate_trade_ids,

        "negative_previous_lags":
            negative_prev,

        "negative_next_leads":
            negative_next,

        "nearest_mean_ms":
            nearest_mean,

        "nearest_median_ms":
            nearest_median,

        "nearest_p95_ms":
            nearest_p95,

        "nearest_p99_ms":
            nearest_p99,

        "nearest_max_ms":
            nearest_max,

        "within_10ms":
            within_10,

        "within_15ms":
            within_15,

        "within_25ms":
            within_25,

        "within_50ms":
            within_50,

        "buy_trades":
            len(buy),

        "sell_trades":
            len(sell),

        "buy_touch_rate":
            buy_touch_rate,

        "sell_touch_rate":
            sell_touch_rate,

        "gate2_pass":
            gate2_pass,

        "output_file":
            str(out_file)
    }


# ======================================================================
# RUN
# ======================================================================

results = []


for hour in HOURS:

    try:

        result = process_hour(
            hour
        )

        results.append(
            result
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

            "hour":
                hour,

            "gate2_pass":
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
print("=" * 112)
print("CANONICAL GATE 2 SUMMARY")
print("=" * 112)


cols = [
    "hour",
    "raw_trades",
    "aligned_trades",
    "trade_coverage",
    "nearest_median_ms",
    "nearest_p99_ms",
    "nearest_max_ms",
    "within_50ms",
    "buy_touch_rate",
    "sell_touch_rate",
    "duplicate_trade_ids",
    "gate2_pass",
]


available = [
    c
    for c in cols
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
            "gate2_pass"
        ]
        .fillna(False)
        .sum()
    ),
    "/",
    len(summary)
)


print()
print(
    "SUMMARY:"
)

print(
    SUMMARY_FILE
)


print()
print("=" * 112)
print("GATE 2 COMPLETE")
print("=" * 112)
