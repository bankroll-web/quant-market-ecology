"""
D09 joint flow -> liquidity interval tape engine.

Exact port of the canonical D09 interval construction from
exp01_replication_d09_batch.py (and d09_joint_flow_liquidity_tape.py).
Behavior is frozen: any refactor must reproduce the frozen
<hour>_d09_joint_flow_liquidity_tape.csv files row-for-row.

Canonical temporal convention (do NOT change):
  - consecutive valid L2 events within one verified episode
  - trades aggregated in (t0, t1] via right/right searchsorted
  - trades sharing t1 exactly are retained and separately counted
    (trades_exactly_at_t1); EXP-01 anchors later exclude them
  - state before the interval = previous event's AFTER state
  - response = current event's AFTER state

Input note (matches canonical behavior): the book CSV is read with
pandas' DEFAULT parser. The frozen d09 outputs embed the resulting
last-ULP artifacts (e.g. spread_t1 0.1000000000058207 vs the d07
source 0.10000000000582077); reading with float_precision='round_trip'
would NOT reproduce the frozen d09 files bit-for-bit.
"""
from pathlib import Path

import numpy as np
import pandas as pd

from src.ingestion.cryptohft import read_cryptohft


def build_intervals(book, trades, hour):
    """Build the D09 joint tape for one hour.

    book:   D07 event-tape DataFrame (already read with the default
            parser, matching the canonical input).
    trades: raw CryptoHFT trades DataFrame.
    hour:   hour label placed first in every record (replication
            canonical; discovery output simply omits it).

    Returns (records_df, counters). records_df matches the frozen
    <hour>_d09_joint_flow_liquidity_tape.csv row-for-row; counters
    match the gate3 summary columns (output_file excluded).
    """
    book = book.copy()
    book["event_time_ms"] = pd.to_numeric(
        book["event_time_ms"], errors="raise"
    ).astype("int64")
    book["episode_id"] = pd.to_numeric(
        book["episode_id"], errors="raise"
    ).astype("int64")
    book = book.sort_values(
        ["episode_id", "event_time_ms"]
    ).reset_index(drop=True)

    trades = trades.copy()
    trades["trade_time_ms"] = pd.to_numeric(
        trades["trade_time"], errors="raise"
    ).astype("int64")
    trades["price_num"] = pd.to_numeric(
        trades["price"], errors="raise"
    )
    trades["qty_num"] = pd.to_numeric(
        trades["quantity"], errors="raise"
    )
    trades["is_buy"] = ~trades["is_buyer_maker"]
    trades["signed_qty"] = np.where(
        trades["is_buy"], trades["qty_num"], -trades["qty_num"]
    )

    records = []
    same_timestamp_trade_count = 0
    used_trade_count = 0

    for ep_id, b in book.groupby("episode_id", sort=True):
        b = b.sort_values("event_time_ms").reset_index(drop=True)

        # Need at least two events to construct one interval.
        if len(b) < 2:
            continue

        ep_start = int(b["event_time_ms"].iloc[0])
        ep_end = int(b["event_time_ms"].iloc[-1])

        et = trades[
            (trades["trade_time_ms"] >= ep_start)
            & (trades["trade_time_ms"] <= ep_end)
        ].sort_values(["trade_time_ms", "trade_id"])

        trade_times = et["trade_time_ms"].to_numpy(dtype=np.int64)

        for i in range(1, len(b)):
            prev = b.iloc[i - 1]
            cur = b.iloc[i]

            t0 = int(prev["event_time_ms"])
            t1 = int(cur["event_time_ms"])

            if t1 <= t0:
                continue

            # Primary convention: (t0, t1]
            left = np.searchsorted(trade_times, t0, side="right")
            right = np.searchsorted(trade_times, t1, side="right")

            ti = et.iloc[left:right]

            n_trades = len(ti)

            if n_trades:
                n_buy = int(ti["is_buy"].sum())
                n_sell = n_trades - n_buy

                buy_qty = float(ti.loc[ti["is_buy"], "qty_num"].sum())
                sell_qty = float(ti.loc[~ti["is_buy"], "qty_num"].sum())

                signed_flow = buy_qty - sell_qty
                total_flow = buy_qty + sell_qty

                qty_sum = float(ti["qty_num"].sum())

                if qty_sum > 0:
                    trade_vwap = float(
                        (ti["price_num"] * ti["qty_num"]).sum() / qty_sum
                    )
                else:
                    trade_vwap = np.nan

                exact_t1 = int((ti["trade_time_ms"] == t1).sum())

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

            # ---------------------------------------------------------
            # STATE BEFORE INTERVAL = PREVIOUS EVENT AFTER-STATE
            # ---------------------------------------------------------
            bid0 = float(prev["best_bid_after"])
            ask0 = float(prev["best_ask_after"])
            mid0 = float(prev["mid_after"])
            spread0 = ask0 - bid0

            bid_depth0 = float(prev["bid_depth5_after"])
            ask_depth0 = float(prev["ask_depth5_after"])

            depth_total0 = bid_depth0 + ask_depth0

            if depth_total0 > 0:
                obi0 = (bid_depth0 - ask_depth0) / depth_total0
            else:
                obi0 = np.nan

            # ---------------------------------------------------------
            # CURRENT BOOK RESPONSE
            # ---------------------------------------------------------
            mid1 = float(cur["mid_after"])
            mid_change = mid1 - mid0
            mid_change_bps = 10000.0 * mid_change / mid0

            bid_add = float(cur["bid_add_qty"])
            ask_add = float(cur["ask_add_qty"])
            bid_remove = float(cur["bid_remove_qty"])
            ask_remove = float(cur["ask_remove_qty"])

            # ---------------------------------------------------------
            # FLOW PRESSURE (descriptive state, NOT trading signals)
            # ---------------------------------------------------------
            eps = 1e-12

            buy_pressure = buy_qty / (ask_depth0 + eps)
            sell_pressure = sell_qty / (bid_depth0 + eps)
            net_pressure = buy_pressure - sell_pressure

            # ---------------------------------------------------------
            # SIMPLE LIQUIDITY RESPONSE COORDINATES
            # ---------------------------------------------------------
            ask_net_response = ask_add - ask_remove
            bid_net_response = bid_add - bid_remove

            records.append({
                "hour": hour,
                "episode_id": int(ep_id),
                "interval_index": i,
                "t0_event_time_ms": t0,
                "t1_event_time_ms": t1,
                "interval_ms": t1 - t0,
                "mid_t0": mid0,
                "best_bid_t0": bid0,
                "best_ask_t0": ask0,
                "spread_t0": spread0,
                "bid_depth5_t0": bid_depth0,
                "ask_depth5_t0": ask_depth0,
                "obi5_t0": obi0,
                "n_trades": n_trades,
                "n_buy_trades": n_buy,
                "n_sell_trades": n_sell,
                "aggressive_buy_qty": buy_qty,
                "aggressive_sell_qty": sell_qty,
                "signed_flow_qty": signed_flow,
                "total_flow_qty": total_flow,
                "trade_vwap": trade_vwap,
                "trades_exactly_at_t1": exact_t1,
                "buy_pressure": buy_pressure,
                "sell_pressure": sell_pressure,
                "net_pressure": net_pressure,
                "bid_add_qty": bid_add,
                "ask_add_qty": ask_add,
                "bid_remove_qty": bid_remove,
                "ask_remove_qty": ask_remove,
                "bid_net_response": bid_net_response,
                "ask_net_response": ask_net_response,
                "total_add_qty": float(cur["total_add_qty"]),
                "total_remove_qty": float(cur["total_remove_qty"]),
                "mid_t1": mid1,
                "mid_change": mid_change,
                "mid_change_bps": mid_change_bps,
                "mid_moved": int(mid_change != 0),
                "spread_t1": float(cur["spread_after"]),
            })

    out = pd.DataFrame(records)

    if len(out):
        out["t0_utc"] = pd.to_datetime(
            out["t0_event_time_ms"], unit="ms", utc=True
        )
        out["t1_utc"] = pd.to_datetime(
            out["t1_event_time_ms"], unit="ms", utc=True
        )

    intervals_with_trade_rows = int((out["n_trades"] > 0).sum())
    positive_flow_intervals = int((out["total_flow_qty"] > 0).sum())
    exact_intervals = int((out["trades_exactly_at_t1"] > 0).sum())
    episodes_with_intervals = int(out["episode_id"].nunique())
    clean_intervals = int((out["trades_exactly_at_t1"] == 0).sum())
    clean_flow = int(
        (
            (out["trades_exactly_at_t1"] == 0)
            & (out["total_flow_qty"] > 0)
        ).sum()
    )

    counters = {
        "valid_l2_intervals": len(out),
        "episodes_with_intervals": episodes_with_intervals,
        "intervals_with_trade_rows": intervals_with_trade_rows,
        "positive_qty_flow_intervals": positive_flow_intervals,
        "trades_assigned": used_trade_count,
        "trades_exactly_at_t1": same_timestamp_trade_count,
        "intervals_with_exact_t1": exact_intervals,
        "clean_intervals": clean_intervals,
        "clean_flow_intervals": clean_flow,
        "interval_ms_mean": float(out["interval_ms"].mean()),
        "interval_ms_median": float(out["interval_ms"].median()),
        "interval_ms_p99": float(out["interval_ms"].quantile(0.99)),
        "interval_ms_max": float(out["interval_ms"].max()),
    }

    return out, counters


def process_hour(hour, book_csv, trade_dir):
    """Build the D09 joint tape for one hour from files.

    book_csv:  D07 event-tape CSV path (read with the DEFAULT parser,
               matching the canonical D09 input).
    trade_dir: directory containing BTCUSDT_trades_<hour>.parquet.

    Returns (records_df, result). result holds the gate3 summary
    counters in column order (output_file excluded).
    """
    book_file = Path(book_csv)

    if not book_file.exists():
        raise FileNotFoundError(str(book_file))

    trade_file = Path(trade_dir) / f"BTCUSDT_trades_{hour}.parquet"

    if not trade_file.exists():
        raise FileNotFoundError(str(trade_file))

    book = pd.read_csv(book_file)
    trades = read_cryptohft(trade_file)

    records_df, counters = build_intervals(book, trades, hour)

    result = {"hour": hour, **counters}

    return records_df, result