"""Public Kraken BTC/USD spot L2; CRC32 top-ten verification, no REST or keys."""
import asyncio
from datetime import datetime
from decimal import Decimal
import json
import time
import zlib
from .live_observer import DepthObserver
from .market_mechanics import MarketMechanics

STREAM='wss://ws.kraken.com/v2'


def checksum(bids,asks):
    parts=[]
    for side,reverse in ((asks,False),(bids,True)):
        for price in sorted(side,reverse=reverse)[:10]:
            for value in (price,side[price]):
                parts.append(format(value,'f').replace('.','').lstrip('0'))
    return zlib.crc32(''.join(parts).encode()) & 0xffffffff


class KrakenObserver(DepthObserver):
    provider='Kraken'
    symbol='BTC/USD'
    product='spot'
    quote_currency='USD'
    validation='CRC32 top 10; ordered WebSocket updates; no exchange sequence ID'

    def __init__(self,depth=1000):
        super().__init__(max_age_ms=2000)
        self.depth=depth
        self.counter=0
        self.trade_messages=0
        self.trade_events=0
        self.last_trade_received_ns=None
        self.trade_subscribed=False
        self.mechanics=MarketMechanics()
        self.model_observation=None

    def invalidate(self,reason):
        super().invalidate(reason)
        self.model_observation=None
        if hasattr(self,'mechanics'):self.mechanics.reset()

    def update_kraken(self,message,received_ns):
        if message.get('channel')!='book' or message.get('type') not in ('snapshot','update'):
            return False
        data=message['data'][0]
        if data.get('symbol')!='BTC/USD':return False
        if message['type']=='snapshot':
            self.invalidate('waiting_for_snapshot')
        elif self.sequence is None:
            return False
        timestamp=data.get('timestamp')
        event_ms=int(datetime.fromisoformat(timestamp.replace('Z','+00:00')).timestamp()*1000) if timestamp else None
        if message['type']=='update' and event_ms is not None and self.event_ms is not None and event_ms<self.event_ms:
            self.invalidate('out_of_order_timestamp');return False
        pre_mid=(max(self.bids)+min(self.asks))/2 if self.bids and self.asks and self.valid else None
        before=(max(self.bids),self.bids[max(self.bids)],min(self.asks),self.asks[min(self.asks)]) if self.valid else None
        changes={}
        for side,key,reverse in ((self.bids,'bids',True),(self.asks,'asks',False)):
            for level in data.get(key,[]):
                price,qty=Decimal(str(level['price'])),Decimal(str(level['qty']))
                if not price.is_finite() or not qty.is_finite() or price<=0 or qty<0:
                    self.invalidate('invalid_level');return False
                if pre_mid is not None and (price>=pre_mid*Decimal('.999') if key=='bids' else price<=pre_mid*Decimal('1.001')):
                    delta=qty-side.get(price,Decimal(0))
                    change_key=('bid' if key=='bids' else 'ask')+('_added_btc' if delta>0 else '_removed_btc')
                    changes[change_key]=changes.get(change_key,0.)+abs(float(delta))
                if qty==0:side.pop(price,None)
                else:side[price]=qty
            for price in sorted(side,reverse=reverse)[self.depth:]:del side[price]
        if not self.bids or not self.asks or max(self.bids)>=min(self.asks):
            self.invalidate('empty_or_crossed_book');return False
        if checksum(self.bids,self.asks)!=int(data['checksum']):
            self.invalidate('checksum_mismatch');return False
        self.counter+=1
        self.sequence=self.counter  # Local counter, explicitly NOT an exchange sequence.
        self.event_ms=event_ms
        self.received_ns=int(received_ns)
        self.valid=True
        self.reason='checksum_verified'
        self.mechanics.record(received_ns,changes, float((max(self.bids)+min(self.asks))/2))
        from .venue_features import observation
        self.model_observation=observation(self,before,received_ns)
        if self.model_observation is not None:
            self.model_observation.update(liquidity_changes=changes,trade_subscription_active=self.trade_subscribed)
        return True

    def observe_trades(self,message,received_ns):
        if message.get('channel')!='trade' or message.get('type')!='update':return []
        accepted=[]
        events=[row for row in message.get('data',[]) if row.get('symbol')==self.symbol]
        if events:
            self.trade_messages+=1
            self.trade_events+=len(events)
            self.last_trade_received_ns=int(received_ns)
            for row in events:
                if self.mechanics.trade(row,received_ns):accepted.append(row)
        return accepted

    def view(self,now_ns):
        result=super().view(now_ns)
        result['model_observation']=self.model_observation if self.valid else None
        result.update(sequence_valid=None,book_validated=self.valid,
                      local_update_count=self.counter,trade_subscription_active=self.trade_subscribed,
                      captured_trade_messages=self.trade_messages,captured_trade_events=self.trade_events,
                      last_trade_received_ns=self.last_trade_received_ns,
                      capture_persistence='ephemeral; lost on restart/redeploy',
                      mechanics=self.mechanics.view(now_ns,result['usable'],self.trade_subscribed))
        return result


async def live_kraken(out,seconds):
    import aiohttp
    observer=KrakenObserver(depth=100)
    deadline=time.monotonic()+seconds
    failures=0
    last_publish=0.
    async with aiohttp.ClientSession(trust_env=True,timeout=aiohttp.ClientTimeout(total=15)) as session:
        while time.monotonic()<deadline:
            observer.trade_subscribed=False
            observer.invalidate('connecting');out.publish(observer,time.time_ns())
            try:
                async with session.ws_connect(STREAM,heartbeat=20,max_msg_size=2**22) as ws:
                    await ws.send_json(dict(method='subscribe',params=dict(channel='book',symbol=['BTC/USD'],depth=observer.depth,snapshot=True)))
                    await ws.send_json(dict(method='subscribe',params=dict(channel='trade',symbol=['BTC/USD'],snapshot=False)))
                    while time.monotonic()<deadline:
                        try:message=await ws.receive(timeout=1)
                        except asyncio.TimeoutError:
                            out.publish(observer,time.time_ns())
                            if observer.received_ns and time.time_ns()-observer.received_ns>30_000_000_000:
                                raise RuntimeError('book_updates_silent_30_seconds')
                            continue
                        if message.type in (aiohttp.WSMsgType.CLOSED,aiohttp.WSMsgType.CLOSE,aiohttp.WSMsgType.ERROR):
                            raise RuntimeError('websocket_closed')
                        if message.type!=aiohttp.WSMsgType.TEXT:continue
                        received=time.time_ns()
                        event=json.loads(message.data,parse_float=Decimal)
                        if event.get('method')=='subscribe' and not event.get('success',False):
                            raise RuntimeError('subscription_rejected: '+str(event.get('error')))
                        if event.get('method')=='subscribe' and event.get('success') and event.get('result',{}).get('channel')=='trade':
                            observer.trade_subscribed=True
                        if event.get('channel')=='trade':
                            out.capture('kraken_trade_message',dict(raw=message.data),received)
                            for trade in observer.observe_trades(event,received):
                                out.capture('kraken_verified_match',dict(qty=float(trade['qty']),side=trade['side'],trade_id=trade['trade_id']),received)
                        if event.get('channel')=='book':
                            out.capture('kraken_message',dict(raw=message.data),received)
                            accepted=observer.update_kraken(event,received)
                            if not accepted and observer.sequence is None:
                                raise RuntimeError(observer.reason)
                            if accepted:
                                if observer.model_observation is not None:out.capture('kraken_model_observation',observer.model_observation,received)
                                failures=0
                        # Apply every update; publish/coalesce the human display at 4 Hz.
                        if time.monotonic()-last_publish>=.25:
                            out.publish(observer,time.time_ns())
                            last_publish=time.monotonic()
            except (aiohttp.ClientError,asyncio.TimeoutError,RuntimeError,ValueError,KeyError) as error:
                observer.trade_subscribed=False
                observer.invalidate('reconnecting')
                out.capture('kraken_disconnect',dict(error=str(error)),time.time_ns());out.publish(observer,time.time_ns())
                failures+=1
                delay=min(60,2**min(failures,6))
                print(f'Kraken unavailable: {error}; retry in {delay}s',flush=True)
                until=min(deadline,time.monotonic()+delay)
                while time.monotonic()<until:
                    out.publish(observer,time.time_ns())
                    await asyncio.sleep(min(1,max(0,until-time.monotonic())))
        observer.invalidate('stopped');out.publish(observer,time.time_ns())
