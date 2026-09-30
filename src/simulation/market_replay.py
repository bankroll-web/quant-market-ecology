"""Build an offline, second-by-second historical observer from verified replay tapes."""
import argparse
import csv
import json
from datetime import datetime, timezone
from pathlib import Path

from .flow_response import NS, trade_tape

HOURS = ('2026-05-25_12', '2026-05-25_18', '2026-05-26_15', '2026-05-26_21')


def build_seconds(book_rows, trades, start_ns, count=3600):
    result = [dict(second=i, book=None, verified_exposure_seconds=0.,
                   buy_btc=0., sell_btc=0., trade_count=0, max_trade_age_ms=None,
                   max_book_age_ms=None, bid_added_btc=0., bid_reduced_btc=0.,
                   ask_added_btc=0., ask_reduced_btc=0.) for i in range(count)]
    for received, signed_qty, age in trades:
        index = (received - start_ns) // NS
        if 0 <= index < count:
            row = result[index]
            row['buy_btc' if signed_qty > 0 else 'sell_btc'] += abs(signed_qty)
            row['trade_count'] += 1
            row['max_trade_age_ms'] = max(age, row['max_trade_age_ms'] if row['max_trade_age_ms'] is not None else age)
    previous = None
    for raw in book_rows:
        received = int(raw['received_time_ns'])
        if previous is not None and received < previous:
            raise ValueError('Book rows must be in receipt order')
        previous = received
        index = (received - start_ns) // NS
        if 0 <= index < count:
            row = result[index]
            age = (received - int(raw['event_time_ms']) * 1_000_000) / 1_000_000
            row['max_book_age_ms'] = max(age, row['max_book_age_ms'] if row['max_book_age_ms'] is not None else age)
            bid, ask = float(raw['post_best_bid']), float(raw['post_best_ask'])
            row['book'] = None if ask <= bid else dict(
                received_time_ns=str(received), episode=int(raw['episode']),
                mid=float(raw['post_mid']), spread=ask-bid,
                bid_depth_btc=float(raw['post_bid_depth_10bps']),
                ask_depth_btc=float(raw['post_ask_depth_10bps']),
                obi=float(raw['post_obi_top']), age_ms=age)
            for side in ('bid', 'ask'):
                row[side + '_added_btc'] += float(raw[side + '_add_qty'])
                row[side + '_reduced_btc'] += float(raw[side + '_remove_qty'])
        # Verified consecutive-update exposure, apportioned across second boundaries.
        a = max(start_ns, received - round(float(raw['exposure_seconds']) * NS))
        b = min(start_ns + count * NS, received)
        while a < b:
            i = (a - start_ns) // NS
            end = min(b, start_ns + (i + 1) * NS)
            result[i]['verified_exposure_seconds'] += (end-a) / NS
            a = end
    for row in result:
        if row['verified_exposure_seconds'] > 1.000001:
            raise ValueError('Overlapping verified exposure')
        row['net_btc'] = row['buy_btc'] - row['sell_btc']
        ages = [v for v in (row['max_book_age_ms'], row['max_trade_age_ms']) if v is not None]
        row['fresh_messages'] = bool(row['book']) and all(0 <= v <= 250 for v in ages)
    return result


def render(data, path):
    payload = json.dumps(data, separators=(',', ':')).replace('</', '<\\/')
    page = '''<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Market Ecology · Real market replay</title><style>body{font:15px system-ui;background:#0b111a;color:#e4edf4;max-width:1150px;margin:25px auto;padding:0 18px}p{line-height:1.5;color:#b4c3d2}.panel{background:#172331;border:1px solid #34485a;border-radius:12px;padding:16px;margin:16px 0}.controls{display:flex;gap:14px;align-items:center;flex-wrap:wrap}select,button{background:#263749;color:white;padding:8px;border:1px solid #587084;border-radius:6px}input{accent-color:#60bcd9;flex:1;min-width:180px}canvas{width:100%;height:170px;display:block}.grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:16px}.metric{display:flex;justify-content:space-between;gap:15px;border-bottom:1px solid #34485a;padding:7px 0;font-variant-numeric:tabular-nums}.warning{color:#e8cc73}@media(max-width:700px){.grid{grid-template-columns:1fr}}</style><h1>Market Ecology · Real market replay</h1><p>Historical BTCUSDT Futures data. Inspect price, spread, net aggressive flow and displayed depth together. This is recorded data from selected hours, not a live connection.</p><div class="panel controls"><label>UTC hour <select id="hour"></select></label><button id="play">Play</button><label id="time"></label><input id="slider" type="range" min="0" max="3599" value="0"><label><input id="zoom" type="checkbox">Show nearby 120 seconds</label></div><div class="panel"><strong>Midprice (USDT)</strong><canvas id="price"></canvas><strong>Spread (USDT)</strong><canvas id="spread"></canvas><strong>Net aggressive flow (BTC / recorded second)</strong><canvas id="flow"></canvas></div><div class="grid"><div class="panel"><h2>Observed market</h2><div id="market"></div></div><div class="panel"><h2>Data quality</h2><div id="quality"></div></div></div><p>Each price/depth point is the last verified post-update book observation recorded within that second. Missing book seconds are left blank; lines stop at episode changes. We do not carry prices across invalid gaps. Trade flow covers the recorded second and can include time outside verified book episodes. Exposure is the amount of verified consecutive-update time inside that second.</p><p>Displayed additions and reductions are changes in visible near-touch quantities; reductions can include executions, modifications or cancellations. The feed does not identify individual institutions, retail traders or makers. Message age is receipt time minus exchange timestamp, including clock differences and capture delay. The 250 ms freshness flag is an exploratory quality threshold.</p><script>const data=PAYLOAD,sel=document.getElementById('hour'),slider=document.getElementById('slider'),zoom=document.getElementById('zoom');let timer=null;for(let name of Object.keys(data)){let o=document.createElement('option');o.value=name;o.textContent=name.replace('_',' ');sel.appendChild(o)}function fmt(x,d=3){return x===null||x===undefined?'Unavailable':Number(x).toLocaleString(undefined,{maximumFractionDigits:d})}function metrics(id,items){document.getElementById(id).innerHTML=items.map(([k,v])=>`<div class="metric"><span>${k}</span><strong>${v}</strong></div>`).join('')}function chart(id,key,color){let el=document.getElementById(id),d=window.devicePixelRatio||1,w=el.clientWidth,h=el.clientHeight;el.width=w*d;el.height=h*d;let c=el.getContext('2d');c.scale(d,d);let t=+slider.value,start=zoom.checked?Math.max(0,t-60):0,end=zoom.checked?Math.min(3599,start+119):3599,rows=data[sel.value].slice(start,end+1),value=r=>key==='net_btc'?r.net_btc:r.book?r.book[key]:null,values=rows.map(value).filter(x=>x!==null),L=72,R=15,T=12,B=24;if(!values.length){c.fillStyle='#b4c3d2';c.fillText('No verified book observations in this range',L,50);return}let lo=Math.min(...values),hi=Math.max(...values),pad=(hi-lo||1)*.1;lo-=pad;hi+=pad;let X=s=>L+(s-start)/Math.max(1,end-start)*(w-L-R),Y=v=>T+(hi-v)/(hi-lo)*(h-T-B);c.font='11px system-ui';for(let i=0;i<3;i++){let v=lo+(hi-lo)*i/2,y=Y(v);c.strokeStyle='#34495a';c.beginPath();c.moveTo(L,y);c.lineTo(w-R,y);c.stroke();c.fillStyle='#b4c3d2';c.fillText(fmt(v,2),3,y+4)}c.strokeStyle=color;c.lineWidth=1.5;c.beginPath();let prior=null;for(let r of rows){let v=value(r);if(v===null){prior=null;continue}let contiguous=prior&&r.second===prior.second+1&&(key==='net_btc'||r.book.episode===prior.book.episode);contiguous?c.lineTo(X(r.second),Y(v)):c.moveTo(X(r.second),Y(v));prior=r}c.stroke();c.setLineDash([4,4]);c.strokeStyle='#ddd';c.beginPath();c.moveTo(X(t),T);c.lineTo(X(t),h-B);c.stroke();c.setLineDash([]);c.fillStyle='#b4c3d2';for(let i=0;i<5;i++){let s=Math.round(start+(end-start)*i/4);c.fillText(String(s),X(s)-8,h-5)}}function draw(){let t=+slider.value,r=data[sel.value][t],b=r.book;document.getElementById('time').textContent=`Second ${t} · ${String(Math.floor(t/60)).padStart(2,'0')}:${String(t%60).padStart(2,'0')} within hour`;metrics('market',[['Midprice',b?fmt(b.mid,2)+' USDT':'No verified book point'],['Spread',b?fmt(b.spread,2)+' USDT':'Unavailable'],['Bid / ask depth within 10 bps',b?fmt(b.bid_depth_btc)+' / '+fmt(b.ask_depth_btc)+' BTC':'Unavailable'],['Top-level imbalance',b?fmt(b.obi):'Unavailable'],['Aggressive buy / sell volume',fmt(r.buy_btc)+' / '+fmt(r.sell_btc)+' BTC'],['Trade rows',r.trade_count],['Bid added / reduced',fmt(r.bid_added_btc)+' / '+fmt(r.bid_reduced_btc)+' BTC'],['Ask added / reduced',fmt(r.ask_added_btc)+' / '+fmt(r.ask_reduced_btc)+' BTC']]);metrics('quality',[['Book point recorded',b?'Yes · episode '+b.episode:'No'],['Verified exposure in this second',fmt(r.verified_exposure_seconds)+' of 1 second'],['Maximum book message age',fmt(r.max_book_age_ms)+' ms'],['Maximum trade message age',fmt(r.max_trade_age_ms)+' ms'],['All observed messages ≤250 ms',b?(r.fresh_messages?'Yes':'No'):'No book observation'],['Exact book receipt timestamp',b?b.received_time_ns+' ns':'Unavailable']]);chart('price','mid','#60bcd9');chart('spread','spread','#e8cc73');chart('flow','net_btc','#f08a5a')}function stop(){clearInterval(timer);timer=null;document.getElementById('play').textContent='Play'}function choose(){stop();slider.value=Math.max(0,data[sel.value].findIndex(r=>r.book));draw()}document.getElementById('play').onclick=()=>{if(timer){stop();return}document.getElementById('play').textContent='Pause';timer=setInterval(()=>{if(+slider.value>=3599){stop();return}slider.value=+slider.value+1;draw()},150)};sel.onchange=choose;slider.oninput=draw;zoom.onchange=draw;addEventListener('resize',draw);choose()</script></html>'''
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(page.replace('PAYLOAD', payload), encoding='utf-8')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--states-dir', type=Path, required=True)
    parser.add_argument('--raw-dir', type=Path, required=True)
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    data = {}
    for hour in HOURS:
        path = args.states_dir / f'BTCUSDT_orderbook_{hour}_observed_changes.csv'
        with path.open() as handle: rows = list(csv.DictReader(handle))
        start = int(datetime.strptime(hour, '%Y-%m-%d_%H').replace(tzinfo=timezone.utc).timestamp()) * NS
        data[hour] = build_seconds(rows, trade_tape(args.raw_dir / f'BTCUSDT_trades_{hour}.parquet'), start)
    render(data, args.out)
    print(json.dumps({h: {'seconds_with_book_point': sum(r['book'] is not None for r in v),
                          'verified_exposure_seconds': sum(r['verified_exposure_seconds'] for r in v)}
                      for h, v in data.items()}, indent=2))


if __name__ == '__main__':
    main()
