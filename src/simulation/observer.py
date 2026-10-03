"""Render an offline, self-contained observer for paired simulation CSV output."""
import argparse
import csv
import json
from pathlib import Path


def render(csv_path, output_path):
    with open(csv_path, newline="") as handle:
        rows = list(csv.DictReader(handle))
    if not rows:
        raise ValueError("No simulation rows")
    numbers = [k for k in rows[0] if k not in ("scenario",)]
    data = [{k: (row[k] if k == "scenario" else float(row[k])) for k in rows[0]} for row in rows]
    payload = json.dumps(data, separators=(",", ":")).replace("</", "<\\/")
    html = """<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Market Ecology · Simulation Observer</title>
<style>
:root{font:15px system-ui,sans-serif;color:#dce6ef;background:#0b111a}body{max-width:1100px;margin:30px auto;padding:0 18px}h1{font-size:26px;margin:0 0 8px}p{color:#a9b8c8;line-height:1.5}.panel{background:#151f2b;border:1px solid #2b3a49;border-radius:12px;padding:18px;margin:18px 0}select,input{accent-color:#66c5dd}select{background:#263749;color:white;border:1px solid #587084;border-radius:6px;padding:7px}canvas{width:100%;height:330px;display:block}.controls{display:flex;gap:18px;align-items:center;flex-wrap:wrap}input[type=range]{flex:1;min-width:220px}.grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:15px}.normal{border-left:4px solid #55b2e1}.withdrawal{border-left:4px solid #f08a5a}.metric{display:grid;grid-template-columns:1fr auto;gap:8px;border-bottom:1px solid #344454;padding:6px 0}.metric span:first-child{color:#b1c0ce}.metric strong{font-variant-numeric:tabular-nums}.small{font-size:12px;color:#879bad}@media(max-width:700px){.grid{grid-template-columns:1fr}}
</style><body><h1>Market Ecology · Simulation Observer</h1><p>Inspect two paired 300-second scenarios. The dashed line marks the 80 BTC buy at second 120. Sample-derived starting scales and assumed agent behavior are documented in the repository. This is a simulated mechanism, not live market data.</p>
<div class="panel"><div class="controls"><label>Measure <select id="measure"><option value="spread">Spread (USDT)</option><option value="ask_depth_btc">Ask depth (BTC)</option><option value="bid_depth_btc">Bid depth (BTC)</option><option value="mid">Midprice (USDT)</option><option value="maker_A_inventory_btc">Maker A inventory (BTC)</option><option value="maker_B_inventory_btc">Maker B inventory (BTC)</option></select></label><label id="time">Second 120</label><input id="slider" type="range" min="0" max="299" value="120"></div><canvas id="plot"></canvas><div class="small">Blue: both makers · Orange: maker B withdraws for 60 seconds</div></div>
<div class="grid"><div class="panel normal"><h2>Both makers</h2><div id="normal"></div></div><div class="panel withdrawal"><h2>Maker B withdrawn</h2><div id="withdrawal"></div></div></div>
<p class="small">Displayed depth is the simulated 770-level band. Mark-to-mid values exclude fees, hedging and risk; they are not trading profits. Background trades are drawn from a state-dependent count model if that mode was used to produce the CSV.</p>
<script>const rows=PAYLOAD;const groups={normal_liquidity:rows.filter(r=>r.scenario==='normal_liquidity'),maker_withdrawal:rows.filter(r=>r.scenario==='maker_withdrawal')};const slider=document.getElementById('slider'),measure=document.getElementById('measure'),canvas=document.getElementById('plot');const colors={normal_liquidity:'#55b2e1',maker_withdrawal:'#f08a5a'};
function current(group,t){return group.find(r=>r.second===t)}function format(x){return Number(x).toLocaleString(undefined,{maximumFractionDigits:3})}
function details(r){const fields=[['Best bid / ask',format(r.bid)+' / '+format(r.ask)],['Spread',format(r.spread)+' USDT'],['Bid / ask depth',format(r.bid_depth_btc)+' / '+format(r.ask_depth_btc)+' BTC'],['Background buys / sells',format(r.background_buy_trades)+' / '+format(r.background_sell_trades)],['Maker A posted / removed',format(r.maker_A_posted_btc)+' / '+format(r.maker_A_cancelled_btc)+' BTC'],['Maker B posted / removed',format(r.maker_B_posted_btc)+' / '+format(r.maker_B_cancelled_btc)+' BTC'],['Maker A / B inventory',format(r.maker_A_inventory_btc)+' / '+format(r.maker_B_inventory_btc)+' BTC'],['Scheduled buy',format(r.shock_buy_qty_btc)+' BTC']];return fields.map(([a,b])=>'<div class="metric"><span>'+a+'</span><strong>'+b+'</strong></div>').join('')}
function draw(){const t=+slider.value,key=measure.value;document.getElementById('time').textContent='Second '+t;document.getElementById('normal').innerHTML=details(current(groups.normal_liquidity,t));document.getElementById('withdrawal').innerHTML=details(current(groups.maker_withdrawal,t));const ratio=window.devicePixelRatio||1,w=canvas.clientWidth,h=canvas.clientHeight;canvas.width=w*ratio;canvas.height=h*ratio;const c=canvas.getContext('2d');c.scale(ratio,ratio);c.clearRect(0,0,w,h);const margin={l:62,r:18,t:20,b:32},X=s=>margin.l+(s/299)*(w-margin.l-margin.r);const values=rows.filter(r=>r.second>=0).map(r=>r[key]),min=Math.min(...values),max=Math.max(...values),pad=(max-min||1)*.08,Y=v=>margin.t+(max+pad-v)/(max-min+2*pad)*(h-margin.t-margin.b);c.strokeStyle='#344454';c.lineWidth=1;for(let i=0;i<5;i++){let y=margin.t+i*(h-margin.t-margin.b)/4;c.beginPath();c.moveTo(margin.l,y);c.lineTo(w-margin.r,y);c.stroke();c.fillStyle='#9bb0c1';c.font='12px system-ui';c.fillText(format(max+pad-i*(max-min+2*pad)/4),4,y+4)}for(const [name,group] of Object.entries(groups)){c.strokeStyle=colors[name];c.lineWidth=2;c.beginPath();group.filter(r=>r.second>=0).forEach((r,i)=>i?c.lineTo(X(r.second),Y(r[key])):c.moveTo(X(r.second),Y(r[key])));c.stroke()}c.setLineDash([5,4]);c.strokeStyle='#ddd';for(const mark of [120,t]){c.beginPath();c.moveTo(X(mark),margin.t);c.lineTo(X(mark),h-margin.b);c.stroke()}c.setLineDash([]);c.fillStyle='#9bb0c1';for(const s of [0,60,120,180,240,299])c.fillText(String(s),X(s)-8,h-8)}slider.addEventListener('input',draw);measure.addEventListener('change',draw);window.addEventListener('resize',draw);draw();</script></body></html>"""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(html.replace("PAYLOAD", payload), encoding="utf-8")
    return len(rows)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--csv", required=True, type=Path)
    parser.add_argument("--out", required=True, type=Path)
    args = parser.parse_args()
    print(f"Wrote {render(args.csv, args.out)} observations to {args.out}")


if __name__ == "__main__":
    main()
