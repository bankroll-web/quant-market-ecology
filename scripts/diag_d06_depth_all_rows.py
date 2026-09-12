"""Diagnostic: verify frozen discovery d06 depth columns == naive loop sum for ALL rows.

Captures top-5 quantities at every recorded state, computes naive-loop and
sum() totals, and compares both against the frozen file.
"""
import sys

sys.path.insert(0, ".")

import numpy as np
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
captured = []


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


def capture():
    top_bids = sorted(bids.items(), reverse=True)[:5]
    top_asks = sorted(asks.items())[:5]
    captured.append(([q for _, q in top_bids], [q for _, q in top_asks]))


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
        capture()
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
    capture()

frozen = pd.read_csv("data/frozen/d06_reconstructed_book_states.csv", float_precision="round_trip")
frozen_bid = frozen["bid_depth_top5"].to_numpy(dtype=float)
frozen_ask = frozen["ask_depth_top5"].to_numpy(dtype=float)

n = len(captured)
loop_bid = np.empty(n)
loop_ask = np.empty(n)
sum_bid = np.empty(n)
sum_ask = np.empty(n)

for i, (qb, qa) in enumerate(captured):
    lb = 0.0
    for v in qb:
        lb += v
    la = 0.0
    for v in qa:
        la += v
    loop_bid[i] = lb
    loop_ask[i] = la
    sum_bid[i] = sum(qb)
    sum_ask[i] = sum(qa)

print(f"states captured: {n}")
print(f"frozen rows:     {len(frozen)}")
print()
print("bid_depth_top5: loop matches frozen:", int((loop_bid == frozen_bid).sum()), "/", n)
print("bid_depth_top5: sum  matches frozen:", int((sum_bid == frozen_bid).sum()), "/", n)
print("ask_depth_top5: loop matches frozen:", int((loop_ask == frozen_ask).sum()), "/", n)
print("ask_depth_top5: sum  matches frozen:", int((sum_ask == frozen_ask).sum()), "/", n)
print()
print("max |loop - frozen| bid:", np.abs(loop_bid - frozen_bid).max())
print("max |sum  - frozen| bid:", np.abs(sum_bid - frozen_bid).max())
print("max |loop - frozen| ask:", np.abs(loop_ask - frozen_ask).max())
print("max |sum  - frozen| ask:", np.abs(sum_ask - frozen_ask).max())