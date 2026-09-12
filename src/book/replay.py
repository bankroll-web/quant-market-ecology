"""
D06 verified order-book reconstruction engine.

Exact port of the canonical replay state machine from
exp01_replication_gate1_canonical.py (and d06_replay_book.py).
Behavior is frozen: any refactor must reproduce the frozen
canonical_book_states CSVs row-for-row.

State machine:
  - snapshot events load the local book and arm the bridge check
  - the first applicable update must bridge snapshot_last_id + 1
  - subsequent updates must satisfy pu == local_update_id
  - invalid bridges / sequence failures invalidate the book until
    the next snapshot
"""
from pathlib import Path

import pandas as pd

from src.ingestion.cryptohft import read_cryptohft


def prepare_events(df):
    """Convert raw rows into ordered logical events (exact D06 grouping).

    Returns (events, snapshot_groups, update_groups). Event ordering is
    (received_time, snapshot-before-update, u / last_update_id).
    """
    df = df.copy()

    df["price_num"] = pd.to_numeric(df["price"], errors="raise")
    df["qty_num"] = pd.to_numeric(df["quantity"], errors="raise")
    df["event_type"] = df["event_type"].astype(str).str.lower()

    snap_rows = df[df["event_type"] == "snapshot"].copy()
    snapshot_groups = []

    for key, g in snap_rows.groupby(
        ["received_time", "event_time", "last_update_id"],
        sort=False,
        dropna=False,
    ):
        received_time, event_time, last_update_id = key
        snapshot_groups.append({
            "received_time": int(received_time),
            "event_time": int(event_time),
            "last_update_id": int(last_update_id),
            "rows": g,
        })

    upd_rows = df[df["event_type"] == "update"].copy()
    update_groups = []

    for key, g in upd_rows.groupby(
        [
            "received_time",
            "event_time",
            "transaction_time",
            "first_update_id",
            "final_update_id",
            "prev_final_update_id",
        ],
        sort=False,
        dropna=False,
    ):
        (
            received_time,
            event_time,
            transaction_time,
            first_update_id,
            final_update_id,
            prev_final_update_id,
        ) = key
        update_groups.append({
            "received_time": int(received_time),
            "event_time": int(event_time),
            "transaction_time": int(transaction_time),
            "U": int(first_update_id),
            "u": int(final_update_id),
            "pu": int(prev_final_update_id),
            "rows": g,
        })

    events = []

    for s in snapshot_groups:
        events.append({"kind": "snapshot", **s})

    for u in update_groups:
        events.append({"kind": "update", **u})

    events.sort(
        key=lambda x: (
            x["received_time"],
            0 if x["kind"] == "snapshot" else 1,
            x.get("u", x.get("last_update_id", 0)),
        )
    )

    return events, snapshot_groups, update_groups


def replay_events(events, hour):
    """Run the exact D06 replay state machine over ordered events.

    Returns (states_df, core_result) where core_result holds the
    canonical audit counters (without hour/raw_rows/snapshot_events/
    update_events, which replay_hour adds).
    """
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
    current_episode_id = 0

    def apply_levels(rows):
        nonlocal level_inserts, level_updates, level_deletes

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

        crossed = int(best_ask <= best_bid)

        top_bids = sorted(bids.items(), reverse=True)[:5]
        top_asks = sorted(asks.items())[:5]

        bid_qty_5 = sum(q for _, q in top_bids)
        ask_qty_5 = sum(q for _, q in top_asks)

        denom = bid_qty_5 + ask_qty_5

        if denom > 0:
            obi5 = (bid_qty_5 - ask_qty_5) / denom
        else:
            obi5 = float("nan")

        mid = (best_bid + best_ask) / 2.0
        spread = best_ask - best_bid

        states.append({
            "hour": hour,
            "episode_id": current_episode_id,
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
            "crossed_book": crossed,
        })

    for event in events:
        # ------------------------------------------------------------
        # SNAPSHOT
        # ------------------------------------------------------------
        if event["kind"] == "snapshot":
            load_snapshot(event["rows"])

            snapshot_last_id = int(event["last_update_id"])
            local_update_id = snapshot_last_id

            waiting_for_bridge = True
            book_valid = False

            snapshots_loaded += 1

            continue

        # ------------------------------------------------------------
        # UPDATE
        # ------------------------------------------------------------
        U = int(event["U"])
        u = int(event["u"])
        pu = int(event["pu"])

        # Fresh snapshot: skip stale events, then demand
        # U <= snapshot_last_id + 1 <= u.
        if waiting_for_bridge:
            if u <= snapshot_last_id:
                stale_updates_skipped += 1
                continue

            target = snapshot_last_id + 1
            bridge_ok = U <= target <= u

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
            current_episode_id += 1

            apply_levels(event["rows"])

            local_update_id = u

            waiting_for_bridge = False
            book_valid = True

            record_state(event)

            continue

        # Invalid book: wait for the next snapshot.
        if not book_valid:
            continue

        # Continuity: exact D06 condition.
        if pu != local_update_id:
            sequence_failures += 1

            book_valid = False

            bids.clear()
            asks.clear()

            local_update_id = None

            continue

        # Valid continuous update.
        apply_levels(event["rows"])

        local_update_id = u

        continuous_updates += 1

        record_state(event)

    states_df = pd.DataFrame(states)

    # ----------------------------------------------------------------
    # AUDIT (exact canonical computation)
    # ----------------------------------------------------------------
    if len(states_df):
        crossed = int(states_df["crossed_book"].sum())
        valid_episodes = int(states_df["episode_id"].nunique())
        spread_mean = float(states_df["spread"].mean())
        spread_median = float(states_df["spread"].median())
        spread_max = float(states_df["spread"].max())
    else:
        crossed = 0
        valid_episodes = 0
        spread_mean = float("nan")
        spread_median = float("nan")
        spread_max = float("nan")

    gate_pass = bool(
        valid_bridges > 0
        and len(states_df) > 0
        and valid_episodes > 0
        and crossed == 0
    )

    core_result = {
        "snapshots_loaded": snapshots_loaded,
        "valid_snapshot_bridges": valid_bridges,
        "invalid_snapshot_bridges": invalid_bridges,
        "stale_updates_skipped": stale_updates_skipped,
        "continuous_updates": continuous_updates,
        "sequence_failures": sequence_failures,
        "valid_states": len(states_df),
        "valid_episodes": valid_episodes,
        "crossed_locked_states": crossed,
        "spread_mean": spread_mean,
        "spread_median": spread_median,
        "spread_max": spread_max,
        "gate1_pass": gate_pass,
    }

    return states_df, core_result


def replay_hour(hour, book_dir):
    """Replay one hour of CryptoHFT order-book data.

    Returns (states_df, result). states_df matches the frozen
    canonical_book_states CSV for that hour row-for-row; result holds
    the canonical audit counters in the gate1 summary column order.
    """
    book_file = Path(book_dir) / f"BTCUSDT_orderbook_{hour}.parquet"

    if not book_file.exists():
        raise FileNotFoundError(str(book_file))

    df = read_cryptohft(book_file)

    events, snapshot_groups, update_groups = prepare_events(df)

    states_df, core_result = replay_events(events, hour)

    result = {
        "hour": hour,
        "raw_rows": len(df),
        "snapshot_events": len(snapshot_groups),
        "update_events": len(update_groups),
        **core_result,
    }

    return states_df, result