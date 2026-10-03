"""Integer-lot, integer-tick FIFO research matching engine; no exchange adapter."""
from collections import defaultdict, deque
from dataclasses import dataclass


@dataclass
class Order:
    identifier: int
    owner: str
    side: str
    price: int
    lots: int


class FIFOBook:
    def __init__(self, tick_usdt=0.1, lot_btc=0.01, maker_fee_bps=0., taker_fee_bps=0.):
        if tick_usdt <= 0 or lot_btc <= 0 or maker_fee_bps < 0 or taker_fee_bps < 0:
            raise ValueError('Invalid units or costs')
        self.tick, self.lot = tick_usdt, lot_btc
        self.maker_fee, self.taker_fee = maker_fee_bps / 10000, taker_fee_bps / 10000
        self.levels = {'bid': defaultdict(deque), 'ask': defaultdict(deque)}
        self.inventory, self.cash = defaultdict(int), defaultdict(float)
        self.filled = defaultdict(int)
        self.next_id = 0

    def best(self, side):
        levels = self.levels[side]
        return (max(levels) if side == 'bid' else min(levels)) if levels else None

    def post(self, owner, side, price, lots):
        if side not in self.levels or type(price) is not int or price <= 0 or type(lots) is not int or lots <= 0:
            raise ValueError('Positive integer ticks/lots and valid side required')
        opposite = self.best('ask' if side == 'bid' else 'bid')
        if opposite is not None and (price >= opposite if side == 'bid' else price <= opposite):
            raise ValueError('Post-only order would cross')
        self.next_id += 1
        order = Order(self.next_id, owner, side, price, lots)
        self.levels[side][price].append(order)
        return order.identifier

    def cancel(self, owner):
        removed = 0
        for levels in self.levels.values():
            for price in list(levels):
                removed += sum(o.lots for o in levels[price] if o.owner == owner)
                queue = deque(o for o in levels[price] if o.owner != owner)
                if queue:
                    levels[price] = queue
                else:
                    del levels[price]
        return removed

    def resting(self, owner, side):
        return sum(o.lots for queue in self.levels[side].values() for o in queue if o.owner == owner)

    def execute(self, owner, side, lots):
        if side not in ('buy', 'sell') or type(lots) is not int or lots < 0:
            raise ValueError('Invalid market order')
        passive = 'ask' if side == 'buy' else 'bid'
        remaining, notional = lots, 0.
        while remaining and self.levels[passive]:
            price = self.best(passive)
            queue = self.levels[passive][price]
            order = queue[0]
            if order.owner == owner:
                # Explicit self-trade prevention: cancel resting order, then continue.
                queue.popleft()
                if not queue:
                    del self.levels[passive][price]
                continue
            quantity = min(remaining, order.lots)
            value = quantity * self.lot * price * self.tick
            sign = 1 if side == 'buy' else -1
            self.inventory[owner] += sign * quantity
            self.inventory[order.owner] -= sign * quantity
            self.cash[owner] -= sign * value + self.taker_fee * value
            self.cash[order.owner] += sign * value - self.maker_fee * value
            self.filled[owner] += quantity
            self.filled[order.owner] += quantity
            order.lots -= quantity
            remaining -= quantity
            notional += value
            if not order.lots:
                queue.popleft()
            if not queue:
                del self.levels[passive][price]
        filled = lots - remaining
        return dict(filled_lots=filled, unfilled_lots=remaining,
                    vwap_usdt=notional / (filled * self.lot) if filled else None)

    def wealth(self, owner, reference_tick):
        return self.cash[owner] + self.inventory[owner] * self.lot * reference_tick * self.tick

    def check(self):
        bid, ask = self.best('bid'), self.best('ask')
        if bid is not None and ask is not None and bid >= ask:
            raise AssertionError('Crossed book')
        if any(o.lots <= 0 for levels in self.levels.values() for queue in levels.values() for o in queue):
            raise AssertionError('Nonpositive resting order')
