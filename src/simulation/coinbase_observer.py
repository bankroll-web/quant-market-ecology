"""Public Coinbase Exchange BTC-USD batched L2 and matches; no credentials."""
import asyncio
import copy
from datetime import datetime
from decimal import Decimal
import json
import math
import time
from .kraken_observer import KrakenObserver

STREAM = 'wss://ws-feed.exchange.coinbase.com'


class CoinbaseObserver(KrakenObserver):
    provider = 'Coinbase Exchange'
    symbol = 'BTC-USD'
    validation = 'Ordered batched L2; no checksum or independently verified book sequence'

    def __init__(self):
        super().__init__()
        self.last_trade_id = None
        self.model_observation = None
        self.feature_samples = 0
        self.feature_first_ns = None

    def invalidate(self, reason):
        super().invalidate(reason)
        self.last_trade_id = None
        self.model_observation = None
        self.feature_samples = 0
        self.feature_first_ns = None

    def update_coinbase(self, event, received_ns):
        if event.get('product_id') != self.symbol:
            return False
        kind = event.get('type')
        if kind not in ('snapshot', 'l2update'):
            return False
        if kind == 'snapshot':
            self.invalidate('waiting_for_timestamped_update')
            levels = [('buy', p, q) for p, q in event['bids']] + [('sell', p, q) for p, q in event['asks']]
            event_ms = None  # Snapshot has no engine time: never invent research freshness.
        else:
            if self.sequence is None:
                return False
            event_ms = int(datetime.fromisoformat(event['time'].replace('Z', '+00:00')).timestamp() * 1000)
            if self.event_ms is not None and event_ms < self.event_ms:
                self.invalidate('out_of_order_timestamp')
                return False
            levels = event['changes']
        mid = (max(self.bids) + min(self.asks)) / 2 if self.valid else None
        before = (max(self.bids), self.bids[max(self.bids)], min(self.asks), self.asks[min(self.asks)]) if self.valid else None
        changes = {}
        for side, price, size in levels:
            if side not in ('buy', 'sell'):
                self.invalidate('invalid_side')
                return False
            p, q = Decimal(price), Decimal(size)
            if not p.is_finite() or not q.is_finite() or p <= 0 or q < 0:
                self.invalidate('invalid_level')
                return False
            book = self.bids if side == 'buy' else self.asks
            if mid is not None and (p >= mid * Decimal('.999') if side == 'buy' else p <= mid * Decimal('1.001')):
                delta = q - book.get(p, Decimal(0))
                key = ('bid' if side == 'buy' else 'ask') + ('_added_btc' if delta > 0 else '_removed_btc')
                changes[key] = changes.get(key, 0.) + abs(float(delta))
            if q == 0:
                book.pop(p, None)
            else:
                book[p] = q  # Absolute size, not a delta. Preserve full snapshot depth.
        if not self.bids or not self.asks or max(self.bids) >= min(self.asks):
            self.invalidate('empty_or_crossed_book')
            return False
        self.counter += 1
        self.sequence = self.counter
        self.event_ms = event_ms
        self.received_ns = received_ns
        self.valid = True
        self.reason = 'ordered_batched_book'
        if event_ms is not None:
            self.mechanics.record(received_ns, changes, float((max(self.bids) + min(self.asks)) / 2))
        if kind == 'l2update' and before is not None:
            bid,ask=max(self.bids),min(self.asks);qb,qa=self.bids[bid],self.asks[ask]
            old_bid,old_qb,old_ask,old_qa=before
            ofi=(qb if bid>=old_bid else 0)-(old_qb if bid<=old_bid else 0)-(qa if ask<=old_ask else 0)+(old_qa if ask>=old_ask else 0)
            midpoint=(bid+ask)/2
            db=sum(q for p,q in self.bids.items() if p>=midpoint*Decimal('.999'))
            da=sum(q for p,q in self.asks.items() if p<=midpoint*Decimal('1.001'))
            depth=db+da
            self.model_observation=None
            if depth>0:
                self.model_observation=dict(provider=self.provider,symbol=self.symbol,source_update_id=self.sequence,
                    event_ns=event_ms*1_000_000,available_ns=received_ns,
                    features=[float((qb-qa)/(qb+qa)),float((db-da)/depth),math.log(float(depth)),float((ask-bid)/midpoint*10000),float(ofi/depth)],
                    midpoint=float(midpoint),best_quote_ofi_btc=float(ofi),depth_btc=float(depth),
                    feature_scope='Full retained Coinbase snapshot and received absolute L2 bundles; no checksum/independent sequence verification')
        if self.model_observation is not None:
            self.feature_samples += 1
            if self.feature_first_ns is None:self.feature_first_ns = received_ns
        return True

    def view(self, now_ns):
        result=super().view(now_ns)
        result['model_observation']=copy.deepcopy(self.model_observation) if self.valid else None
        result['training_capture']=dict(status='collecting' if self.valid else 'paused',feature_bundles=self.feature_samples,first_received_ns=self.feature_first_ns,usable_labeled_examples=None,qualified=False,reason='Feature count is not labeled sample count; offline integrity and continuity audit required')
        return result

    def observe_match(self, event, received_ns):
        if event.get('product_id') != self.symbol or event.get('type') not in ('last_match', 'match'):
            return
        trade_id = int(event['trade_id'])
        if event['type'] == 'last_match':
            self.last_trade_id = trade_id
            return  # Historical subscription seed is not a new observed trade.
        if self.last_trade_id is not None:
            if trade_id <= self.last_trade_id:
                return
            if trade_id != self.last_trade_id + 1:
                raise RuntimeError('trade_id_gap')
        self.last_trade_id = trade_id
        self.trade_messages += 1
        self.trade_events += 1
        self.last_trade_received_ns = received_ns
        side = event['side']  # Coinbase side identifies the resting MAKER.
        if side not in ('buy', 'sell'):
            raise ValueError('invalid trade side')
        self.mechanics.trade(dict(trade_id=trade_id, qty=event['size'],
                                  side='buy' if side == 'sell' else 'sell'), received_ns)


def publish_coinbase(out, observer, now_ns):
    # Keep the authoritative full book, but bound display/scenario copies to 100 levels.
    display = copy.copy(observer)
    display.bids = {p: observer.bids[p] for p in sorted(observer.bids, reverse=True)[:100]}
    display.asks = {p: observer.asks[p] for p in sorted(observer.asks)[:100]}
    display.validation += '; display and scenarios limited to 100 levels/side'
    out.publish(display, now_ns)


async def live_coinbase(out, seconds):
    import aiohttp
    observer = CoinbaseObserver()
    deadline = time.monotonic() + seconds
    failures = 0
    last_publish = 0.
    async with aiohttp.ClientSession(trust_env=True, timeout=aiohttp.ClientTimeout(total=15)) as session:
        while time.monotonic() < deadline:
            observer.trade_subscribed = False
            observer.invalidate('connecting')
            publish_coinbase(out, observer, time.time_ns())
            try:
                async with session.ws_connect(STREAM, heartbeat=20, max_msg_size=2**24) as ws:
                    await ws.send_json(dict(type='subscribe', product_ids=[observer.symbol],
                                            channels=['level2_batch', 'matches', 'heartbeat']))
                    connected = time.monotonic()
                    while time.monotonic() < deadline:
                        try:
                            message = await ws.receive(timeout=1)
                        except asyncio.TimeoutError:
                            publish_coinbase(out, observer, time.time_ns())
                            if time.monotonic() - connected > 30 and (observer.received_ns is None or time.time_ns() - observer.received_ns > 30_000_000_000):
                                raise RuntimeError('book_updates_silent_30_seconds')
                            continue
                        if message.type in (aiohttp.WSMsgType.CLOSED, aiohttp.WSMsgType.CLOSE, aiohttp.WSMsgType.ERROR):
                            raise RuntimeError('websocket_closed')
                        if message.type != aiohttp.WSMsgType.TEXT:
                            continue
                        received = time.time_ns()
                        event = json.loads(message.data)
                        out.capture('coinbase_message', dict(raw=message.data), received)
                        kind = event.get('type')
                        if kind == 'error':
                            raise RuntimeError('subscription_rejected: ' + str(event.get('message')))
                        if kind == 'subscriptions':
                            observer.trade_subscribed = any(c['name'] == 'matches' and observer.symbol in c.get('product_ids', []) for c in event['channels'])
                        observer.observe_match(event, received)
                        if kind in ('snapshot', 'l2update') and event.get('product_id') == observer.symbol:
                            if not observer.update_coinbase(event, received):
                                raise RuntimeError(observer.reason)
                            if observer.model_observation is not None:
                                out.capture('coinbase_model_observation', observer.model_observation, received)
                            failures = 0
                        if time.monotonic() - connected > 30 and (observer.received_ns is None or received - observer.received_ns > 30_000_000_000):
                            raise RuntimeError('book_updates_silent_30_seconds')
                        if time.monotonic() - last_publish >= .25:
                            publish_coinbase(out, observer, time.time_ns())
                            last_publish = time.monotonic()
            except (aiohttp.ClientError, asyncio.TimeoutError, RuntimeError, ValueError, KeyError) as error:
                observer.trade_subscribed = False
                observer.invalidate('reconnecting')
                out.capture('coinbase_disconnect', dict(error=str(error)), time.time_ns())
                failures += 1
                delay = min(60, 2**min(failures, 6))
                print(f'Coinbase unavailable: {error}; retry in {delay}s', flush=True)
                until = min(deadline, time.monotonic() + delay)
                while time.monotonic() < until:
                    publish_coinbase(out, observer, time.time_ns())
                    await asyncio.sleep(min(1, max(0, until-time.monotonic())))
        observer.invalidate('stopped')
        publish_coinbase(out, observer, time.time_ns())
