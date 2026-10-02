"""Public Kraken BTC/USD spot L2; CRC32 top-ten verification, no REST or keys."""
import asyncio
from datetime import datetime
from decimal import Decimal
import json
import time
import zlib
from .live_observer import DepthObserver

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
        for side,key,reverse in ((self.bids,'bids',True),(self.asks,'asks',False)):
            for level in data.get(key,[]):
                price,qty=Decimal(str(level['price'])),Decimal(str(level['qty']))
                if not price.is_finite() or not qty.is_finite() or price<=0 or qty<0:
                    self.invalidate('invalid_level');return False
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
        return True

    def view(self,now_ns):
        result=super().view(now_ns)
        result.update(sequence_valid=None,book_validated=self.valid,
                      local_update_count=self.counter)
        return result


async def live_kraken(out,seconds):
    import aiohttp
    observer=KrakenObserver()
    deadline=time.monotonic()+seconds
    failures=0
    async with aiohttp.ClientSession(trust_env=True,timeout=aiohttp.ClientTimeout(total=15)) as session:
        while time.monotonic()<deadline:
            observer.invalidate('connecting');out.publish(observer,time.time_ns())
            try:
                async with session.ws_connect(STREAM,heartbeat=20,max_msg_size=2**22) as ws:
                    await ws.send_json(dict(method='subscribe',params=dict(channel='book',symbol=['BTC/USD'],depth=1000,snapshot=True)))
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
                        if event.get('channel')=='book':
                            out.capture('kraken_message',dict(raw=message.data),received)
                            accepted=observer.update_kraken(event,received)
                            if not accepted and observer.sequence is None:
                                raise RuntimeError(observer.reason)
                            if accepted:failures=0
                        out.publish(observer,time.time_ns())
            except (aiohttp.ClientError,asyncio.TimeoutError,RuntimeError,ValueError,KeyError) as error:
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
