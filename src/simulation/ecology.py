"""Small, reproducible agent-based BTC limit-order-book ecology experiment.

Run: python -m src.simulation.ecology --config configs/simulation_v1_demo.json --out data/processed/simulation_v1
Only initial scale and background trade flow are anchored to the supplied samples.
Cancellation, replenishment, agent behavior and stress size are explicit assumptions.
"""
import argparse
import csv
import json
import math
import random
from collections import defaultdict
from pathlib import Path


TICK = 0.1
LEVELS = 770  # Approximately 10 bps at the observed BTC price and $0.10 tick.
SHOCK_SECOND = 120
SHOCK_QTY = 80.0
WITHDRAW_SECONDS = 60
STEPS = 300


def poisson(rng, rate):
    cutoff, product, count = math.exp(-rate), 1.0, 0
    while product > cutoff:
        count += 1
        product *= rng.random()
    return count - 1


def calibrate(files):
    import pandas as pd
    frames = [pd.read_csv(path) for path in files]
    joined = pd.concat(frames, ignore_index=True)
    active = joined[joined.trade_count > 0]
    # All rows are valid book seconds. This conditional flow scale is illustrative:
    # the original files have many invalid seconds that cannot be treated as zero flow.
    return {
        "reference_mid": float(joined.mid.median()),
        "top_bid_qty": float(joined.bid_top_qty.median()),
        "top_ask_qty": float(joined.ask_top_qty.median()),
        "depth_bid_10bps": float(joined.bid_depth_10bps.median()),
        "depth_ask_10bps": float(joined.ask_depth_10bps.median()),
        "background_trades_per_second": float(active.trade_count.median()),
        "mean_trade_qty_btc": float(active.total_aggressive_qty.sum() / active.trade_count.sum()),
        "source_valid_book_seconds": len(joined),
    }


class Book:
    def __init__(self, params):
        self.reference_tick = round(params["reference_mid"] / TICK)
        self.bids, self.asks = defaultdict(dict), defaultdict(dict)
        self.target = {
            "bid": [params["top_bid_qty"]] + [(params["depth_bid_10bps"] - params["top_bid_qty"]) / (LEVELS - 1)] * (LEVELS - 1),
            "ask": [params["top_ask_qty"]] + [(params["depth_ask_10bps"] - params["top_ask_qty"]) / (LEVELS - 1)] * (LEVELS - 1),
        }
        self.inventory = {"maker_A": 0., "maker_B": 0.}
        self.cash = {"maker_A": 0., "maker_B": 0.}
        self.executed_qty = {"maker_A": 0., "maker_B": 0.}
        for side in ("bid", "ask"):
            for level in range(LEVELS):
                price = self.price_tick(side, level)
                for maker in ("maker_A", "maker_B"):
                    self.levels(side)[price][maker] = self.target[side][level] / 2

    def levels(self, side):
        return self.bids if side == "bid" else self.asks

    def price_tick(self, side, level):
        return self.reference_tick + (1 + level if side == "ask" else -level)

    def best(self, side):
        book = self.levels(side)
        return (max(book) if side == "bid" else min(book)) if book else None

    def depth(self, side):
        return sum(q for owners in self.levels(side).values() for q in owners.values())

    def cancel(self, maker, fraction):
        removed = 0.
        for book in (self.bids, self.asks):
            for price in list(book):
                if maker in book[price]:
                    cut = book[price][maker] * fraction
                    book[price][maker] -= cut
                    removed += cut
                    if book[price][maker] < 1e-10:
                        del book[price][maker]
                if not book[price]:
                    del book[price]
        return removed

    def replenish(self, maker, fraction):
        posted = 0.
        for side in ("bid", "ask"):
            book = self.levels(side)
            for level, target in enumerate(self.target[side]):
                price = self.price_tick(side, level)
                existing = book.get(price, {}).get(maker, 0.)
                desired = target / 2
                add = max(0., (desired - existing) * fraction)
                if add > 1e-9:
                    book[price][maker] = existing + add
                    posted += add
        return posted

    def execute(self, side, requested):
        """Aggressive buy consumes asks; sell consumes bids, pro rata within a price."""
        passive_side = "ask" if side == "buy" else "bid"
        book = self.levels(passive_side)
        remaining, value = requested, 0.
        while remaining > 1e-10 and book:
            price = self.best(passive_side)
            owners = book[price]
            available = sum(owners.values())
            fill_total = min(remaining, available)
            remaining -= fill_total
            value += fill_total * price * TICK
            for owner, qty in list(owners.items()):
                fill = fill_total * qty / available
                self.executed_qty[owner] += fill
                self.inventory[owner] += -fill if side == "buy" else fill
                self.cash[owner] += fill * price * TICK * (1 if side == "buy" else -1)
                owners[owner] -= fill
                if owners[owner] < 1e-10:
                    del owners[owner]
            if not owners:
                del book[price]
        filled = requested - remaining
        return filled, (value / filled if filled else None)

    def state(self, second, scenario, cancelled=0., posted=0.):
        bid, ask = self.best("bid"), self.best("ask")
        if bid is None or ask is None or bid >= ask:
            raise RuntimeError("Empty or crossed simulated book")
        mid = (bid + ask) * TICK / 2
        row = {"scenario": scenario, "second": second, "bid": bid * TICK,
               "ask": ask * TICK, "mid": mid, "spread": (ask - bid) * TICK,
               "bid_depth_btc": self.depth("bid"), "ask_depth_btc": self.depth("ask"),
               "cancelled_btc": cancelled, "posted_btc": posted}
        for maker in self.inventory:
            row[maker + "_inventory_btc"] = self.inventory[maker]
            row[maker + "_mark_to_mid_usdt"] = self.cash[maker] + self.inventory[maker] * mid
        return row


def common_flow(params, seed):
    rng = random.Random(seed)
    flow = []
    for _ in range(STEPS):
        flow.append([("buy" if rng.random() < .5 else "sell",
                      min(1., rng.expovariate(1 / max(params["mean_trade_qty_btc"], .001))))
                     for _ in range(poisson(rng, params["background_trades_per_second"]))])
    return flow


def run(params, flow, withdrawal):
    book = Book(params)
    scenario = "maker_withdrawal" if withdrawal else "normal_liquidity"
    rows, shock = [], None
    rows.append(book.state(-1, scenario))
    for second, trades in enumerate(flow):
        cancelled = book.cancel("maker_A", .002)
        if second == SHOCK_SECOND and withdrawal:
            cancelled += book.cancel("maker_B", 1.)
        elif not (withdrawal and SHOCK_SECOND <= second < SHOCK_SECOND + WITHDRAW_SECONDS):
            cancelled += book.cancel("maker_B", .002)
        for side, qty in trades:
            book.execute(side, qty)
        if second == SHOCK_SECOND:
            before = book.state(second, scenario)
            filled, vwap = book.execute("buy", SHOCK_QTY)
            shock = {"pre_shock_mid": before["mid"], "pre_shock_ask": before["ask"],
                     "requested_qty_btc": SHOCK_QTY, "filled_qty_btc": filled,
                     "execution_vwap": vwap,
                     "slippage_vs_pre_ask_bps": (vwap / before["ask"] - 1) * 10_000}
        # Quotes arrive after trades; reserve the shock-second state to see immediate impact.
        if second != SHOCK_SECOND:
            posted = book.replenish("maker_A", .08)
            if not (withdrawal and SHOCK_SECOND <= second < SHOCK_SECOND + WITHDRAW_SECONDS):
                posted += book.replenish("maker_B", .08)
        else:
            posted = 0.
        rows.append(book.state(second, scenario, cancelled, posted))
    shock["immediate_mid_move_bps"] = (rows[SHOCK_SECOND + 1]["mid"] / shock["pre_shock_mid"] - 1) * 10_000
    shock["immediate_spread"] = rows[SHOCK_SECOND + 1]["spread"]
    shock["ask_depth_10s_after_btc"] = rows[SHOCK_SECOND + 11]["ask_depth_btc"]
    shock["ask_depth_30s_after_btc"] = rows[SHOCK_SECOND + 31]["ask_depth_btc"]
    shock["scenario"] = scenario
    shock["maker_end_state"] = {maker: {"inventory_btc": book.inventory[maker],
        "mark_to_mid_usdt": book.cash[maker] + book.inventory[maker] * rows[-1]["mid"],
        "executed_qty_btc": book.executed_qty[maker]} for maker in book.inventory}
    return rows, shock


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--input", nargs="+", type=Path)
    source.add_argument("--config", type=Path)
    parser.add_argument("--out", required=True, type=Path)
    parser.add_argument("--seed", type=int, default=7)
    args = parser.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)
    params = calibrate(args.input) if args.input else json.loads(args.config.read_text())["calibration_from_valid_samples"]
    flow = common_flow(params, args.seed)
    all_rows, shocks = [], []
    for withdrawal in (False, True):
        rows, shock = run(params, flow, withdrawal)
        all_rows.extend(rows)
        shocks.append(shock)
    with open(args.out / "simulated_ecology.csv", "w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(all_rows[0]))
        writer.writeheader()
        writer.writerows(all_rows)
    report = {"calibration_from_valid_samples": params, "seed": args.seed,
              "assumptions": {"tick_usdt": TICK, "levels_each_side": LEVELS,
                  "makers": 2, "maker_cancel_fraction_per_second": .002,
                  "maker_replenish_fraction_of_deficit_per_second": .08,
                  "shock_second": SHOCK_SECOND, "shock_side": "buy",
                  "shock_qty_btc": SHOCK_QTY, "withdrawal_duration_seconds": WITHDRAW_SECONDS,
                  "maker_withdrawal": "Maker B cancels all visible orders at shock and stops quoting for 60 seconds.",
                  "reference_price": "Fixed; no fundamental value process, latency, fees or derivatives."},
              "results": shocks, "interpretation": "Mechanistic counterfactual in a stylized book, not a calibrated forecast or maker profit estimate."}
    (args.out / "simulation_report.json").write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
