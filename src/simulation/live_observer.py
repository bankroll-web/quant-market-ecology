"""Read-only Binance USD-M BTCUSDT depth observer, fixture replay and dashboard."""
import argparse
import asyncio
from collections import deque
from decimal import Decimal
import functools
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
import json
import math
import os
from pathlib import Path
import threading
import time

REST = 'https://fapi.binance.com/fapi/v1/depth?symbol=BTCUSDT&limit=1000'
STREAM = 'wss://fstream.binance.com/public/stream?streams=btcusdt@depth@100ms'


class DepthObserver:
    provider='Binance'
    symbol='BTCUSDT'
    product='USD-M futures'
    quote_currency='USDT'
    validation='Futures snapshot bridge and pu update continuity'
    def __init__(self, max_age_ms=250):
        self.max_age_ms = max_age_ms
        self.bids, self.asks = {}, {}
        self.sequence = None
        self.bridging = False
        self.received_ns = None
        self.event_ms = None
        self.reason = 'waiting_for_snapshot'
        self.valid = False

    def invalidate(self, reason):
        self.bids.clear(); self.asks.clear()
        self.sequence = None
        self.valid = False
        self.bridging = False
        self.reason = reason

    def snapshot(self, data):
        self.invalidate('waiting_for_bridge')
        self.bids = {Decimal(p): Decimal(q) for p, q in data['bids'] if Decimal(q) > 0}
        self.asks = {Decimal(p): Decimal(q) for p, q in data['asks'] if Decimal(q) > 0}
        self.sequence = int(data['lastUpdateId'])
        self.bridging = True

    def update(self, message, received_ns):
        data = message.get('data', message)
        if data.get('s') != 'BTCUSDT' or data.get('e') != 'depthUpdate':
            return False
        if self.sequence is None:
            return False
        first, final = int(data['U']), int(data['u'])
        if first > final:
            self.invalidate('invalid_update_range'); return False
        if self.bridging:
            if final < self.sequence:
                return False
            # Futures rule differs from the frozen historical diagnostic.
            if not first <= self.sequence <= final:
                self.invalidate('snapshot_bridge_gap'); return False
        else:
            if final <= self.sequence:
                return False  # Duplicate/stale event must not refresh health.
            if int(data['pu']) != self.sequence:
                self.invalidate('sequence_gap'); return False
        for side, key in ((self.bids, 'b'), (self.asks, 'a')):
            for price, quantity in data[key]:
                p, q = Decimal(price), Decimal(quantity)
                if not p.is_finite() or not q.is_finite() or p <= 0 or q < 0:
                    self.invalidate('invalid_level'); return False
                if q == 0:
                    side.pop(p, None)
                else:
                    side[p] = q
        if not self.bids or not self.asks or max(self.bids) >= min(self.asks):
            self.invalidate('empty_or_crossed_book'); return False
        self.sequence = final
        self.bridging = False
        self.received_ns, self.event_ms = int(received_ns), int(data['E'])
        self.valid, self.reason = True, 'synchronized'
        return True

    def view(self, now_ns):
        since = (now_ns - self.received_ns) / 1e6 if self.received_ns is not None else None
        age = (self.received_ns - self.event_ms * 1_000_000) / 1e6 if self.received_ns is not None and self.event_ms is not None else None
        usable = self.valid and since is not None and age is not None and 0 <= since <= self.max_age_ms and 0 <= age <= self.max_age_ms
        research_usable = usable and age <= 250 and since <= 250
        status = self.reason if not self.valid else ('fresh' if research_usable else 'live_delayed') if usable else 'stale_or_clock_warning'
        out = dict(status=status, sequence_valid=self.valid, usable=usable,
                   research_usable=research_usable, display_max_age_ms=self.max_age_ms,
                   last_update_id=self.sequence, last_received_ns=self.received_ns,
                   receipt_minus_event_ms=age, silence_ms=since,
                   bid=None, ask=None, mid=None, spread=None, top_obi=None,
                   bid_depth_10bps=None, ask_depth_10bps=None, bids=[], asks=[])
        if usable:
            bid, ask = max(self.bids), min(self.asks)
            mid = (bid + ask) / 2
            qb, qa = self.bids[bid], self.asks[ask]
            out.update(bid=float(bid), ask=float(ask), mid=float(mid), spread=float(ask-bid),
                top_obi=float((qb-qa)/(qb+qa)),
                bid_depth_10bps=float(sum(q for p,q in self.bids.items() if p >= mid*Decimal('.999'))),
                ask_depth_10bps=float(sum(q for p,q in self.asks.items() if p <= mid*Decimal('1.001'))),
                bids=[[float(p),float(self.bids[p])] for p in sorted(self.bids,reverse=True)[:10]],
                asks=[[float(p),float(self.asks[p])] for p in sorted(self.asks)[:10]])
        return out


class DashboardHandler(SimpleHTTPRequestHandler):
    def end_headers(self):
        self.send_header('Cache-Control', 'no-store, max-age=0')
        self.send_header('X-Observer-Time-Ms', str(time.time_ns() // 1_000_000))
        super().end_headers()


class Output:
    def __init__(self, directory, mode='live', archive_directory=None):
        from .live_ecology import LiveEcology
        from .ecology_dashboard import PAGE as ECOLOGY_PAGE
        self.ecology = LiveEcology()
        self.mode = mode
        self.directory = Path(directory)
        self.directory.mkdir(parents=True, exist_ok=True)
        from .capture_archive import CaptureArchive
        archive_path = Path(archive_directory or self.directory.parent / (self.directory.name + '-archive'))
        if archive_path.resolve().is_relative_to(self.directory.resolve()):
            raise ValueError('archive must be outside the public dashboard directory')
        self.archive = CaptureArchive(archive_path)
        self.history = deque(maxlen=600)
        (self.directory/'index.html').write_text(PAGE)
        (self.directory/'ecology.html').write_text(ECOLOGY_PAGE)

    def capture(self, kind, payload, received_ns):
        return self.archive.append(kind, payload, received_ns)

    def publish(self, observer, now_ns):
        view = observer.view(now_ns)
        view['archive'] = self.archive.view()
        view['capture_persistence'] = view['archive']['persistence']
        self.history.append(dict(time_ms=now_ns//1_000_000, mid=view['mid']))
        market=dict(provider=observer.provider,symbol=observer.symbol,product=observer.product,quote_currency=observer.quote_currency,validation=observer.validation)
        content = dict(mode=self.mode, **market, read_only=True,
                       generated_ns=now_ns, **view, history=list(self.history))
        tmp = self.directory/'state.tmp'
        tmp.write_text(json.dumps(content))
        tmp.replace(self.directory/'state.json')
        ecology = dict(mode=self.mode, **market, generated_ns=now_ns, **self.ecology.update(observer,now_ns))
        for key in ('trade_subscription_active','captured_trade_messages','captured_trade_events','last_trade_received_ns','capture_persistence','mechanics','archive','model_observation'):
            if key in view:ecology[key]=view[key]
        from .live_model_status import assess
        ecology['model_status']=assess(market,view,now_ns)
        ecology['models']={k:v.replace('USDT',observer.quote_currency) for k,v in ecology['models'].items()}
        tmp = self.directory/'ecology.tmp'
        tmp.write_text(json.dumps(ecology))
        tmp.replace(self.directory/'ecology.json')


def retry_delay(error):
    status = getattr(error, 'status', None)
    if status not in (418, 429):
        return 2.
    headers = getattr(error, 'headers', None) or {}
    try:
        supplied = float(headers.get('Retry-After', ''))
    except (ValueError, TypeError):
        supplied = 0.
    if not math.isfinite(supplied):
        supplied = 0.
    return max(300. if status == 418 else 60., supplied)


async def live(out, seconds):
    import aiohttp
    observer = DepthObserver(max_age_ms=2000)
    deadline = time.monotonic() + seconds
    async with aiohttp.ClientSession(trust_env=True, timeout=aiohttp.ClientTimeout(total=15)) as session:
        while time.monotonic() < deadline:
            observer.invalidate('connecting')
            out.publish(observer,time.time_ns())
            try:
                async with session.ws_connect(STREAM, heartbeat=20, max_msg_size=2**20) as ws:
                    queue = asyncio.Queue(maxsize=5000)
                    async def receive():
                        async for message in ws:
                            if message.type != aiohttp.WSMsgType.TEXT:
                                continue
                            event = message.json()
                            received = time.time_ns()
                            if queue.full():
                                raise RuntimeError('buffer_overflow')
                            out.capture('depth',event,received)
                            queue.put_nowait((event,received))
                        raise RuntimeError('websocket_closed')
                    task = asyncio.create_task(receive())
                    try:
                        # Stream is already buffering before requesting the snapshot.
                        async with session.get(REST) as response:
                            response.raise_for_status()
                            snapshot = await response.json()
                        out.capture('snapshot',snapshot,time.time_ns())
                        observer.snapshot(snapshot)
                        while time.monotonic() < deadline:
                            if task.done():
                                task.result()
                            try:
                                event, received = await asyncio.wait_for(queue.get(), timeout=.1)
                                observer.update(event,received)
                                if observer.sequence is None:
                                    raise RuntimeError(observer.reason)
                            except asyncio.TimeoutError:
                                pass
                            out.publish(observer,time.time_ns())
                    finally:
                        task.cancel()
                        await asyncio.gather(task,return_exceptions=True)
            except (aiohttp.ClientError, asyncio.TimeoutError, RuntimeError, ValueError, KeyError) as error:
                restricted = getattr(error, 'status', None) == 451
                observer.invalidate('restricted_location' if restricted else 'provider_cooldown' if getattr(error,'status',None) in (418,429) else 'reconnecting')
                out.capture('disconnect',dict(error=str(error)),time.time_ns())
                out.publish(observer,time.time_ns())
                print('Connection unavailable:',str(error),flush=True)
                if restricted:
                    return
                delay = retry_delay(error)
                # Publish unavailable state throughout cooldown without opening new connections.
                until = min(deadline, time.monotonic()+delay)
                print(f'Retrying after at least {delay:.0f} seconds',flush=True)
                while time.monotonic() < until:
                    out.publish(observer,time.time_ns())
                    await asyncio.sleep(min(1,max(0,until-time.monotonic())))
        observer.invalidate('stopped')
        out.publish(observer,time.time_ns())


def replay(path, out):
    observer = DepthObserver()
    # Network captures buffer depth before snapshot. Reproduce that bootstrap order.
    buffered = []
    for line in Path(path).read_text().splitlines():
        event = json.loads(line)
        kind, received = event['kind'], int(event['received_ns'])
        if kind == 'snapshot':
            observer.snapshot(event['payload'])
            for payload, timestamp in buffered:
                observer.update(payload,timestamp)
            buffered.clear()
        elif kind == 'depth':
            if observer.sequence is None:
                buffered.append((event['payload'],received))
            else:
                observer.update(event['payload'],received)
        elif kind == 'disconnect':
            observer.invalidate('disconnected'); buffered.clear()
        out.publish(observer,received)
    return observer


PAGE = '''<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Market ecology observer</title><style>body{font:17px system-ui;background:#101827;color:#e8edf6;max-width:1100px;margin:30px auto;padding:20px}.cards{display:flex;flex-wrap:wrap;gap:12px}.card{background:#1c2a40;padding:16px;border-radius:12px;min-width:160px}strong{font-size:25px}canvas{width:100%;height:300px;background:#1c2a40;margin-top:20px}table{display:inline-table;width:48%;padding:12px;text-align:right}p{line-height:1.5;color:#bccadd}</style><h1>Bitcoin market ecology · Read-only observer</h1><p><a href="ecology.html" style="color:#63d0c6">Open the live simulation laboratory →</a></p><p>Live view accepts synchronized updates up to 2 seconds old and labels delay; the stricter research-quality cutoff remains 250 ms. Recorded or live order-book observations. No trading decisions or orders. Empty prices mean the book is unavailable or stale.</p><p id="market"></p><div id="status">Waiting for observations…</div><div class="cards" id="cards"></div><canvas id="chart"></canvas><div id="depth"></div><p>This view shows anonymous displayed liquidity. It does not identify institutions or dealers. Depth is limited to the snapshot and received updates; timestamp age includes clock differences.</p><script>const fmt=x=>x==null?'—':Number(x).toFixed(3);async function draw(){try{const started=performance.now();const r=await fetch('state.json',{cache:'no-store',signal:AbortSignal.timeout(2000)});if(!r.ok)throw Error('unavailable');const s=await r.json();document.getElementById('market').textContent=s.provider+' · '+s.symbol+' · '+s.product+' · '+s.validation;const serverNow=Number(r.headers.get('X-Observer-Time-Ms'));const pageAge=serverNow-s.generated_ns/1e6;const transit=performance.now()-started;if(s.mode!=='replay'&&(!serverNow||pageAge<0||pageAge+transit>2000)){document.getElementById('status').textContent='Observer offline · data not current';document.getElementById('cards').textContent='';document.getElementById('depth').textContent='';document.getElementById('chart').getContext('2d').clearRect(0,0,2000,2000);return}document.getElementById('status').textContent=(s.usable?'LIVE · '+(s.research_usable?'fast feed':'delayed feed'):s.status)+' · receipt/event age '+fmt(s.receipt_minus_event_ms)+' ms · silence '+fmt(s.silence_ms)+' ms · update '+s.last_update_id;document.getElementById('cards').innerHTML=[['Midpoint',s.mid],['Spread',s.spread],['Top imbalance',s.top_obi],['Bid depth BTC',s.bid_depth_10bps],['Ask depth BTC',s.ask_depth_10bps]].map(([k,v])=>`<div class="card">${k}<br><strong>${fmt(v)}</strong></div>`).join('');document.getElementById('depth').innerHTML=[['Bids',s.bids],['Asks',s.asks]].map(([label,rows])=>`<table><tr><th>${label}: price</th><th>BTC</th></tr>${rows.map(([p,q])=>`<tr><td>${fmt(p)}</td><td>${fmt(q)}</td></tr>`).join('')}</table>`).join('');let el=document.getElementById('chart');el.width=el.clientWidth;el.height=300;let c=el.getContext('2d'),v=s.history.filter(x=>x.mid!=null);if(!v.length)return;let lo=Math.min(...v.map(x=>x.mid)),hi=Math.max(...v.map(x=>x.mid));if(hi===lo){lo-=.1;hi+=.1}let first=s.history[0].time_ms,last=s.history.at(-1).time_ms;c.strokeStyle='#63d0c6';c.beginPath();let active=false;for(let p of s.history){if(p.mid==null){active=false;continue}let x=20+(p.time_ms-first)/Math.max(1,last-first)*(el.width-40),y=20+(hi-p.mid)/(hi-lo)*260;if(active)c.lineTo(x,y);else c.moveTo(x,y);active=true}c.stroke();c.fillStyle='#e8edf6';c.fillText('Midpoint · '+fmt(lo)+' to '+fmt(hi)+' '+s.quote_currency,20,15)}catch(e){document.getElementById('status').textContent='Cannot load observations';document.getElementById('cards').textContent='';document.getElementById('depth').textContent=''}}draw();setInterval(draw,500)</script></html>'''


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out',type=Path,required=True)
    parser.add_argument('--archive',type=Path,default=os.environ.get('CAPTURE_ARCHIVE_DIR'))
    parser.add_argument('--seconds',type=float,default=60)
    parser.add_argument('--replay',type=Path)
    parser.add_argument('--provider',choices=('binance','kraken','coinbase'),default='binance')
    parser.add_argument('--serve',action='store_true')
    parser.add_argument('--port',type=int,default=int(os.environ.get('PORT','8765')))
    parser.add_argument('--host',default='127.0.0.1',help='Use 0.0.0.0 only in an authorized cloud deployment')
    args=parser.parse_args()
    if not math.isfinite(args.seconds) or args.seconds<=0:
        parser.error('seconds must be positive and finite')
    out=Output(args.out, 'replay' if args.replay else 'live', args.archive)
    server=None
    if args.serve:
        server=ThreadingHTTPServer((args.host,args.port),functools.partial(DashboardHandler,directory=str(args.out)))
        threading.Thread(target=server.serve_forever,daemon=True).start()
        print(f'Observer: http://{args.host}:{args.port}',flush=True)
    try:
        if args.replay:
            replay(args.replay,out)
        else:
            if args.provider=='coinbase':
                from .coinbase_observer import live_coinbase
                asyncio.run(live_coinbase(out,args.seconds))
            elif args.provider=='kraken':
                from .kraken_observer import live_kraken
                asyncio.run(live_kraken(out,args.seconds))
            else:
                asyncio.run(live(out,args.seconds))
    finally:
        out.archive.close()
        if server: server.shutdown()


if __name__ == '__main__': main()
