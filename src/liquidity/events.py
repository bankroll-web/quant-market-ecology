"""
D07 liquidity event tape engine.

Exact port of the canonical D07 replay from
exp01_replication_d07_batch.py (and d07_liquidity_event_tape.py).
Behavior is frozen: any refactor must reproduce the frozen
<hour>_d07_liquidity_event_tape.csv files row-for-row.

D07 re-runs the D06 state machine independently (it does not consume the
D06 book-states output) and, for every valid event, measures the liquidity
change: add/remove quantities, level add/remove/modify counts, before/after
top-5 depth, and derived ecology measures.
"""
from pathlib import Path

import numpy as np
import pandas as pd

from src.book.replay import prepare_events
from src.ingestion.cryptohft import read_cryptohft


def top_depth(book, side, n):
    """Sum of the n best levels (exact canonical computation, sum())."""
    if side == "bid":
        levels = sorted(book.items(), reverse=True)[:n]
    else:
        levels = sorted(book.items())[:n]

    return sum(q for _, q in levels)


def replay_liquidity_events(events, hour):
    """Run the exact D07 replay over ordered events.

    Returns (records_df, core_result) where core_result holds the
    canonical audit counters (without hour/raw_rows/snapshots/
    update_events, which process_hour adds).
    """
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

            old_q = float(book.get(p, 0.0))

            delta = new_q - old_q

            # --------------------------------------------------------
            # QUANTITY INCREASE
            # --------------------------------------------------------
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

            # --------------------------------------------------------
            # QUANTITY DECREASE
            # --------------------------------------------------------
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

            # --------------------------------------------------------
            # APPLY NEW STATE
            # --------------------------------------------------------
            if new_q == 0:
                book.pop(p, None)
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
            "ask_levels_modified": ask_levels_modified,
        }

    for event in events:
        # ------------------------------------------------------------
        # SNAPSHOT
        # ------------------------------------------------------------
        if event["kind"] == "snapshot":
            load_snapshot(event["rows"])

            snapshot_last_id = int(event["last_update_id"])
            local_update_id = snapshot_last_id

            waiting_bridge = True
            book_valid = False

            continue

        U = int(event["U"])
        u = int(event["u"])
        pu = int(event["pu"])

        # ------------------------------------------------------------
        # SNAPSHOT -> FIRST APPLICABLE UPDATE
        # ------------------------------------------------------------
        if waiting_bridge:
            if u <= snapshot_last_id:
                stale_skipped += 1
                continue

            target = snapshot_last_id + 1

            if not (U <= target <= u):
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

            before_mid = (before_bid + before_ask) / 2.0

            before_bid_depth5 = top_depth(bids, "bid", 5)
            before_ask_depth5 = top_depth(asks, "ask", 5)

            changes = apply_and_measure(event["rows"])

            local_update_id = u
            waiting_bridge = False
            book_valid = True

        else:
            if not book_valid:
                continue

            # --------------------------------------------------------
            # UPDATE -> UPDATE CONTINUITY
            # --------------------------------------------------------
            if pu != local_update_id:
                sequence_failures += 1

                book_valid = False

                bids.clear()
                asks.clear()

                local_update_id = None

                continue

            before_bid = max(bids)
            before_ask = min(asks)

            before_mid = (before_bid + before_ask) / 2.0

            before_bid_depth5 = top_depth(bids, "bid", 5)
            before_ask_depth5 = top_depth(asks, "ask", 5)

            changes = apply_and_measure(event["rows"])

            local_update_id = u

        # ------------------------------------------------------------
        # VALID POST-UPDATE STATE
        # ------------------------------------------------------------
        if not bids or not asks:
            continue

        best_bid = max(bids)
        best_ask = min(asks)

        mid = (best_bid + best_ask) / 2.0

        spread = best_ask - best_bid

        bid_depth5 = top_depth(bids, "bid", 5)
        ask_depth5 = top_depth(asks, "ask", 5)

        depth_denom = bid_depth5 + ask_depth5

        if depth_denom > 0:
            obi5 = (bid_depth5 - ask_depth5) / depth_denom
        else:
            obi5 = np.nan

        # ------------------------------------------------------------
        # EVENT-LEVEL ECOLOGY MEASURES
        # ------------------------------------------------------------
        total_add = changes["bid_add_qty"] + changes["ask_add_qty"]
        total_remove = changes["bid_remove_qty"] + changes["ask_remove_qty"]

        liquidity_net = total_add - total_remove

        # Positive = bid-side net support relative to ask-side.
        directional_liquidity = (
            changes["bid_add_qty"]
            - changes["bid_remove_qty"]
            - changes["ask_add_qty"]
            + changes["ask_remove_qty"]
        )

        records.append({
            "hour": hour,
            "episode_id": episode_id,
            "received_time_ns": event["received_time"],
            "event_time_ms": event["event_time"],
            "transaction_time_ms": event["transaction_time"],
            "first_update_id": U,
            "final_update_id": u,
            "prev_final_update_id": pu,
            "changed_levels": len(event["rows"]),
            "best_bid_before": before_bid,
            "best_ask_before": before_ask,
            "mid_before": before_mid,
            "best_bid_after": best_bid,
            "best_ask_after": best_ask,
            "mid_after": mid,
            "mid_change": mid - before_mid,
            "spread_after": spread,
            "bid_depth5_before": before_bid_depth5,
            "ask_depth5_before": before_ask_depth5,
            "bid_depth5_after": bid_depth5,
            "ask_depth5_after": ask_depth5,
            "obi5_after": obi5,
            **changes,
            "total_add_qty": total_add,
            "total_remove_qty": total_remove,
            "net_displayed_liquidity": liquidity_net,
            "directional_liquidity": directional_liquidity,
            "crossed_book": int(best_bid >= best_ask),
        })

    out = pd.DataFrame(records)

    if len(out):
        out["event_time_utc"] = pd.to_datetime(
            out["event_time_ms"], unit="ms", utc=True
        )
        out["transaction_time_utc"] = pd.to_datetime(
            out["transaction_time_ms"], unit="ms", utc=True
        )

        crossed = int(out["crossed_book"].sum())
        valid_episodes = int(out["episode_id"].nunique())
        moved = out["mid_change"] != 0
        move_rate = float(moved.mean())
        bid_add_total = float(out["bid_add_qty"].sum())
        ask_add_total = float(out["ask_add_qty"].sum())
        bid_remove_total = float(out["bid_remove_qty"].sum())
        ask_remove_total = float(out["ask_remove_qty"].sum())
    else:
        crossed = 0
        valid_episodes = 0
        move_rate = np.nan
        bid_add_total = np.nan
        ask_add_total = np.nan
        bid_remove_total = np.nan
        ask_remove_total = np.nan

    gate_pass = bool(
        valid_bridges > 0
        and len(out) > 0
        and valid_episodes > 0
        and crossed == 0
    )

    core_result = {
        "valid_bridges": valid_bridges,
        "invalid_bridges": invalid_bridges,
        "stale_skipped": stale_skipped,
        "sequence_failures": sequence_failures,
        "valid_event_records": len(out),
        "valid_episodes": valid_episodes,
        "crossed_states": crossed,
        "mid_move_rate": move_rate,
        "bid_add_total": bid_add_total,
        "ask_add_total": ask_add_total,
        "bid_remove_total": bid_remove_total,
        "ask_remove_total": ask_remove_total,
        "gate_pass": gate_pass,
    }

    return out, core_result


def process_hour(hour, book_dir):
    """Build the D07 liquidity event tape for one hour.

    Returns (records_df, result). records_df matches the frozen
    <hour>_d07_liquidity_event_tape.csv row-for-row; result holds the
    canonical audit counters in the gate1b summary column order.
    """
    book_file = Path(book_dir) / f"BTCUSDT_orderbook_{hour}.parquet"

    if not book_file.exists():
        raise FileNotFoundError(str(book_file))

    df = read_cryptohft(book_file)

    events, snapshots, updates = prepare_events(df, lowercase_side=True)

    records_df, core_result = replay_liquidity_events(events, hour)

    result = {
        "hour": hour,
        "raw_rows": len(df),
        "snapshots": len(snapshots),
        "update_events": len(updates),
        **core_result,
    }

    return records_df, result