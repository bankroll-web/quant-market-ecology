"""
D09B touch-distance liquidity ecology engine.

Exact port of the canonical D09B replay from
exp01_replication_d09b_one_hour.py (and d09b_touch_distance_ecology.py).
Behavior is frozen: any refactor must reproduce the frozen
<hour>_d09b_touch_distance_book_events.csv and
<hour>_d09b_joint_flow_touch_ecology.csv files row-for-row.

D09B re-runs the D06/D07 state machine independently (it does not consume
the D07 event tape) and, for every valid event, classifies each level
change by its distance from the PRE-event touch in ticks:
  - bucket 0_5  : 0..5 ticks
  - bucket 6_20 : 6..20 ticks
  - bucket gt20 : >20 ticks
A new price improving the current touch produces a negative raw distance;
economically it belongs at the touch, so it clamps to 0 ticks.

The tick size is inferred from the first 1000 snapshot rows (minimum
positive difference between sorted unique prices), exactly as canonical.

Input note (matches canonical behavior): the D09 joint tape is read with
pandas' DEFAULT parser, so the frozen d09b joint outputs embed the same
last-ULP artifacts as the frozen d09 files (e.g. spread_t0
0.0999999999912688); reading with float_precision='round_trip' would NOT
reproduce them bit-for-bit.
"""
from pathlib import Path

import numpy as np
import pandas as pd

from src.book.replay import prepare_events
from src.ingestion.cryptohft import read_cryptohft

BUCKETS = ["0_5", "6_20", "gt20"]
SIDES = ["bid", "ask"]


def infer_tick_size(df):
    """Infer the price tick from the first 1000 snapshot rows (canonical)."""
    snap_sample = df[df["event_type"] == "snapshot"].head(1000)

    sample_prices = np.sort(snap_sample["price_num"].unique())

    diffs = np.diff(sample_prices)
    diffs = diffs[diffs > 1e-9]

    if len(diffs) == 0:
        raise RuntimeError("Could not infer tick size.")

    return float(np.min(diffs))


def get_distance_bucket(side, price, best_bid, best_ask, tick_size):
    """Distance in ticks from the pre-event touch, clamped at 0.

    Returns (ticks, bucket) with bucket in 0_5 / 6_20 / gt20.
    """
    if side == "ask":
        raw_ticks = (price - best_ask) / tick_size
    else:
        raw_ticks = (best_bid - price) / tick_size

    ticks = max(0, int(round(raw_ticks)))

    if ticks <= 5:
        bucket = "0_5"
    elif ticks <= 20:
        bucket = "6_20"
    else:
        bucket = "gt20"

    return ticks, bucket


def blank_changes():
    """Empty per-event change counters (canonical key order)."""
    d = {}

    for side in SIDES:
        for action in ["add", "remove"]:
            for bucket in BUCKETS:
                d[f"{side}_{action}_{bucket}_qty"] = 0.0
                d[f"{side}_{action}_{bucket}_levels"] = 0

    d["price_improving_bid_updates"] = 0
    d["price_improving_ask_updates"] = 0

    return d


def replay_touch_events(events, tick_size):
    """Run the exact D09B replay over ordered events.

    Returns (evt_df, core_result) where core_result holds the canonical
    audit counters (without the merge-derived counters, which
    process_hour adds).
    """
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

        for r in rows.itertuples(index=False):
            p = float(r.price_num)
            q = float(r.qty_num)

            if q <= 0:
                continue

            if r.side == "bid":
                bids[p] = q
            elif r.side == "ask":
                asks[p] = q

    def apply_and_classify(rows, best_bid_before, best_ask_before):
        """Apply an update event to the book and classify by distance.

        Mutates the replay book state (bids/asks) exactly like the
        canonical replay; returns the change counters dict.
        """
        ch = blank_changes()

        for r in rows.itertuples(index=False):
            side = r.side
            p = float(r.price_num)
            new_q = float(r.qty_num)

            book = bids if side == "bid" else asks

            old_q = float(book.get(p, 0.0))
            delta = new_q - old_q

            # ---------------------------------------------------------
            # DISTANCE FROM PRE-EVENT TOUCH
            # ---------------------------------------------------------
            ticks, bucket = get_distance_bucket(
                side, p, best_bid_before, best_ask_before, tick_size
            )

            # ---------------------------------------------------------
            # PRICE-IMPROVING LEVEL
            # ---------------------------------------------------------
            if side == "bid":
                if p > best_bid_before:
                    ch["price_improving_bid_updates"] += 1
            else:
                if p < best_ask_before:
                    ch["price_improving_ask_updates"] += 1

            # ---------------------------------------------------------
            # ADDITION / INCREASE
            # ---------------------------------------------------------
            if delta > 0:
                ch[f"{side}_add_{bucket}_qty"] += delta
                ch[f"{side}_add_{bucket}_levels"] += 1

            # ---------------------------------------------------------
            # DECREASE / REMOVAL
            # ---------------------------------------------------------
            elif delta < 0:
                removed = abs(delta)
                ch[f"{side}_remove_{bucket}_qty"] += removed
                ch[f"{side}_remove_{bucket}_levels"] += 1

            # ---------------------------------------------------------
            # APPLY BOOK STATE
            # ---------------------------------------------------------
            if new_q == 0:
                book.pop(p, None)
            else:
                book[p] = new_q

        return ch

    for event in events:
        # -------------------------------------------------------------
        # SNAPSHOT
        # -------------------------------------------------------------
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

        # -------------------------------------------------------------
        # FIRST UPDATE AFTER SNAPSHOT
        # -------------------------------------------------------------
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
        best_bid_before = max(bids)
        best_ask_before = min(asks)

        mid_before = (best_bid_before + best_ask_before) / 2.0

        # -------------------------------------------------------------
        # APPLY + CLASSIFY
        # -------------------------------------------------------------
        changes = apply_and_classify(
            event["rows"], best_bid_before, best_ask_before
        )

        local_update_id = u

        if not bids or not asks:
            book_valid = False
            continue

        # -------------------------------------------------------------
        # POST-EVENT STATE
        # -------------------------------------------------------------
        best_bid_after = max(bids)
        best_ask_after = min(asks)

        mid_after = (best_bid_after + best_ask_after) / 2.0

        row = {
            "episode_id": episode_id,
            "event_time_ms": int(event["event_time"]),
            "transaction_time_ms": int(event["transaction_time"]),
            "received_time_ns": int(event["received_time"]),
            "first_update_id": U,
            "final_update_id": u,
            "prev_final_update_id": pu,
            "best_bid_before": best_bid_before,
            "best_ask_before": best_ask_before,
            "best_bid_after": best_bid_after,
            "best_ask_after": best_ask_after,
            "mid_before": mid_before,
            "mid_after": mid_after,
            "mid_change": mid_after - mid_before,
            **changes,
        }

        # -------------------------------------------------------------
        # NET RESPONSE BY SIDE / DISTANCE
        # -------------------------------------------------------------
        for side in SIDES:
            for bucket in BUCKETS:
                row[f"{side}_net_{bucket}_qty"] = (
                    row[f"{side}_add_{bucket}_qty"]
                    - row[f"{side}_remove_{bucket}_qty"]
                )

        records.append(row)

    out = pd.DataFrame(records)

    if len(out):
        out["event_time_utc"] = pd.to_datetime(
            out["event_time_ms"], unit="ms", utc=True
        )

    core_result = {
        "valid_bridges": valid_bridges,
        "invalid_bridges": invalid_bridges,
        "stale_skipped": stale_skipped,
        "sequence_failures": sequence_failures,
        "valid_event_records": len(out),
    }

    return out, core_result


def process_hour(hour, book_dir, d09_csv):
    """Build the D09B touch-distance ecology for one hour from files.

    book_dir: directory containing BTCUSDT_orderbook_<hour>.parquet.
    d09_csv:  D09 joint-tape CSV path (read with the DEFAULT parser,
              matching the canonical D09B input).

    Returns (evt_df, aug_df, result):
      - evt_df matches the frozen <hour>_d09b_touch_distance_book_events.csv
        row-for-row (discovery output has no hour column either way)
      - aug_df matches the frozen <hour>_d09b_joint_flow_touch_ecology.csv
        row-for-row (hour column present only when the D09 input has it)
      - result holds the canonical audit + merge counters
    """
    book_file = Path(book_dir) / f"BTCUSDT_orderbook_{hour}.parquet"

    if not book_file.exists():
        raise FileNotFoundError(str(book_file))

    d09_file = Path(d09_csv)

    if not d09_file.exists():
        raise FileNotFoundError(str(d09_file))

    df = read_cryptohft(book_file)

    # Canonical preprocessing order: lowercase, numeric, tick inference.
    df["event_type"] = df["event_type"].astype(str).str.lower()
    df["side"] = df["side"].astype(str).str.lower()
    df["price_num"] = pd.to_numeric(df["price"], errors="raise")
    df["qty_num"] = pd.to_numeric(df["quantity"], errors="raise")

    tick_size = infer_tick_size(df)

    events, snapshots, updates = prepare_events(df, lowercase_side=True)

    evt_df, core_result = replay_touch_events(events, tick_size)

    # -------------------------------------------------------------
    # MERGE INTO D09 JOINT FLOW TAPE (default parser, canonical)
    # -------------------------------------------------------------
    joint = pd.read_csv(d09_file)

    joint["episode_id"] = pd.to_numeric(
        joint["episode_id"], errors="raise"
    ).astype("int64")

    joint["t1_event_time_ms"] = pd.to_numeric(
        joint["t1_event_time_ms"], errors="raise"
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
        "price_improving_ask_updates",
    ]

    aug = joint.merge(
        evt_df[touch_cols],
        left_on=["episode_id", "t1_event_time_ms"],
        right_on=["episode_id", "event_time_ms"],
        how="left",
        validate="many_to_one",
    )

    match_rate = float(aug["event_time_ms"].notna().mean())

    # -------------------------------------------------------------
    # PRIMARY TIMESTAMP-CLEAN SUBSET (canonical definitions)
    # -------------------------------------------------------------
    clean_intervals = int((aug["trades_exactly_at_t1"] == 0).sum())
    removed_exact_t1 = int((aug["trades_exactly_at_t1"] != 0).sum())

    clean_flow_intervals = int(
        (
            (aug["trades_exactly_at_t1"] == 0)
            & (aug["total_flow_qty"] > 0)
        ).sum()
    )

    signed_clean_intervals = int(
        (
            (aug["trades_exactly_at_t1"] == 0)
            & (aug["total_flow_qty"] > 0)
            & (aug["signed_flow_qty"] != 0)
        ).sum()
    )

    gate_pass = bool(
        core_result["valid_bridges"] > 0
        and core_result["sequence_failures"] == 0
        and len(evt_df) > 0
        and len(aug) == len(joint)
        and match_rate == 1.0
    )

    result = {
        "hour": hour,
        **core_result,
        "d09_rows": len(joint),
        "augmented_rows": len(aug),
        "touch_response_match": match_rate,
        "all_intervals": len(aug),
        "clean_intervals": clean_intervals,
        "removed_exact_t1": removed_exact_t1,
        "clean_flow_intervals": clean_flow_intervals,
        "signed_clean_intervals": signed_clean_intervals,
        "gate_pass": gate_pass,
    }

    return evt_df, aug, result