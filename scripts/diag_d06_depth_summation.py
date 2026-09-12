"""Diagnostic: verify discovery d06 depth columns used naive (loop) summation.

Replays hour 00 with a record_state that captures the top-5 quantities at
the first state, then checks which summation reproduces the frozen value.
"""
import sys

sys.path.insert(0, ".")

import pandas as pd

from src.book.replay import prepare_events
from src.ingestion.cryptohft import read_cryptohft

df = read_cryptohft("data/raw/BTCUSDT_orderbook_2026-05-25_00.parquet")
events, _, _ = prepare_events(df)

bids = {}
asks = {}
book_valid = False
waiting_for_bridge = False
local_update_id = None
snapshot_last_id = None
captured = None


def apply_levels(rows):
    for row in rows.itertuples(index=False):
        side = row.side
        price = float(row.price_num)
        qty = float(row.qty_num)
        book = bids if side == "bid" else asks
        if qty == 0.0:
            if price in book:
                del book[price]
        else:
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


for event in events:
    if event["kind"] == "snapshot":
        load_snapshot(event["rows"])
        snapshot_last_id = int(event["last_update_id"])
        local_update_id = snapshot_last_id
        waiting_for_bridge = True
        book_valid = False
        continue

    U = int(event["U"])
    u = int(event["u"])
    pu = int(event["pu"])

    if waiting_for_bridge:
        if u <= snapshot_last_id:
            continue
        target = snapshot_last_id + 1
        if not (U <= target <= u):
            waiting_for_bridge = False
            book_valid = False
            bids.clear()
            asks.clear()
            local_update_id = None
            snapshot_last_id = None
            continue
        apply_levels(event["rows"])
        local_update_id = u
        waiting_for_bridge = False
        book_valid = True
        if captured is None:
            top_bids = sorted(bids.items(), reverse=True)[:5]
            top_asks = sorted(asks.items())[:5]
            captured = {
                "top_bids": [q for _, q in top_bids],
                "top_asks": [q for _, q in top_asks],
            }
        continue

    if not book_valid:
        continue

    if pu != local_update_id:
        book_valid = False
        bids.clear()
        asks.clear()
        local_update_id = None
        continue

    apply_levels(event["rows"])
    local_update_id = u

frozen = pd.read_csv("data/frozen/d06_reconstructed_book_states.csv", float_precision="round_trip")
frozen_bid = frozen.loc[0, "bid_depth_top5"]
frozen_ask = frozen.loc[0, "ask_depth_top5"]

qb = captured["top_bids"]
qa = captured["top_asks"]

loop_bid = 0.0
for v in qb:
    loop_bid += v
loop_ask = 0.0
for v in qa:
    loop_ask += v

print("top-5 bid qty:", [repr(v) for v in qb])
print("top-5 ask qty:", [repr(v) for v in qa])
print("frozen bid_depth_top5:", repr(frozen_bid))
print("loop  bid_depth_top5 :", repr(loop_bid), " match:", loop_bid == frozen_bid)
print("sum   bid_depth_top5 :", repr(sum(qb)), " match:", sum(qb) == frozen_bid)
print("frozen ask_depth_top5:", repr(frozen_ask))
print("loop  ask_depth_top5 :", repr(loop_ask), " match:", loop_ask == frozen_ask)
print("sum   ask_depth_top5 :", repr(sum(qa)), " match:", sum(qa) == frozen_ask)