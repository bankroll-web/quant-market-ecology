"""Synthetic participant ecology initialized from live displayed liquidity."""
import math
from decimal import Decimal
from .clustered_flow import hawkes
from .learning_book import FIFOBook


def rollout(bids, asks, withdrawal=False, signed_gamma=0., seed=71, seconds=30):
    """Frozen live anchor, synthetic arrivals; FIFO queues and ownership are invented."""
    book=FIFOBook(maker_fee_bps=1.,taker_fee_bps=2.)
    dropped=0.
    for side, levels in [('bid',bids),('ask',asks)]:
        for price in sorted(levels,reverse=side=='bid')[:20]:
            lots=int(levels[price]/Decimal(str(book.lot)))
            dropped+=float(levels[price])-lots*book.lot
            if lots:
                # Direction-preserving tick rounding; no claim about actual queue priority.
                tick=math.floor(float(price)/book.tick+1e-7) if side=='bid' else math.ceil(float(price)/book.tick-1e-7)
                book.post('anonymous_background',side,tick,lots)
    if book.best('bid') is None or book.best('ask') is None:
        return dict(status='insufficient_quantized_depth',trace=[],participants=[])
    anchor=(book.best('bid')+book.best('ask'))//2
    base_mid=(book.best('bid')+book.best('ask'))/2*book.tick
    events=[[] for _ in range(seconds)]
    for timestamp,side,lots in hawkes(seed,seconds):
        events[int(timestamp)].append((side,lots))
    trace=[]
    fees=0.
    for second in range(seconds):
        for maker in ['maker_A','maker_B']:
            book.cancel(maker)
            if withdrawal and maker=='maker_B' and 10<=second<20:
                continue
            inventory=book.inventory[maker]
            skew=max(-4,min(4,inventory//5))
            center=anchor-skew  # Assumed inventory control, not an HJB optimum.
            for side in ('bid','ask'):
                capacity=max(0,20-inventory if side=='bid' else 20+inventory)
                for distance in (2,4):
                    lots=min(2,capacity)
                    if not lots:break
                    price=center+distance if side=='ask' else center-distance
                    other=book.best('bid' if side=='ask' else 'ask')
                    if other is not None:
                        price=max(price,other+1) if side=='ask' else min(price,other-1)
                    book.post(maker,side,price,lots);capacity-=lots
        before=(book.best('bid')+book.best('ask'))/2*book.tick if book.best('bid') is not None and book.best('ask') is not None else None
        orders=[('simulated_retail',side,lots) for side,lots in events[second]]
        if second==10:orders.append(('simulated_institution','buy',100))
        if second==20:orders.append(('simulated_institution','sell',100))
        for owner,side,lots in orders:
            book.execute(owner,side,lots)
        mid=(book.best('bid')+book.best('ask'))/2*book.tick if book.best('bid') is not None and book.best('ask') is not None else None
        hedge=0
        if before is not None and mid is not None and signed_gamma:
            hedge=int(round(-signed_gamma*(mid-before)/book.lot))
            inventory=book.inventory['assumed_gamma_dealer']
            hedge=max(-50-inventory,min(50-inventory,hedge))
            book.execute('assumed_gamma_dealer','buy' if hedge>0 else 'sell',abs(hedge))
        book.check()
        mid=(book.best('bid')+book.best('ask'))/2*book.tick if book.best('bid') is not None and book.best('ask') is not None else None
        # Total marked wealth equals negative paid fees by cash/inventory conservation.
        fees=-sum(book.cash.values())
        trace.append(dict(second=second,midpoint=mid,move_bps=(mid/base_mid-1)*10000 if mid is not None else None,
                          maker_A_inventory_btc=book.inventory['maker_A']*book.lot,
                          maker_B_inventory_btc=book.inventory['maker_B']*book.lot,
                          hedge_signed_btc=hedge*book.lot))
    participants=[dict(role=owner,inventory_btc=book.inventory[owner]*book.lot,
                       cash_usdt=book.cash[owner],marked_wealth_usdt=book.wealth(owner,anchor),
                       filled_btc=book.filled[owner]*book.lot)
                  for owner in ['anonymous_background','maker_A','maker_B','simulated_retail',
                                'simulated_institution','assumed_gamma_dealer']]
    return dict(status='synthetic',seed=seed,seconds=seconds,trace=trace,participants=participants,
                total_paid_fees_usdt=fees,inventory_sum_btc=sum(book.inventory.values())*book.lot,
                quantization_dropped_btc=dropped,initial_midpoint=base_mid,
                assumed_gamma_btc_per_usdt=signed_gamma,
                assumptions='20 levels/side; 0.10 USDT tick, 0.01 BTC lot; invented FIFO queues; frozen anchor; Hawkes mu=1.2, alpha_self=.5, alpha_cross=.1, beta=1.5; institution buys 1 BTC at 10s, sells 1 BTC at 20s; maker cap ±.20 BTC; dealer cap ±.50 BTC; maker fee 1 bp, taker 2 bps; inventory-skew baseline, no trained policy; no latency or background replenishment.')
