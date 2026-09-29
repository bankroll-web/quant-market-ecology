"""Paired size sweep of the stylized maker-withdrawal experiment.

Run: python -m src.simulation.impact_sweep --config configs/simulation_v1_demo.json --out data/processed/impact_sweep
"""
import argparse
import csv
import json
from pathlib import Path

from .ecology import SHOCK_SECOND, common_flow, run

SIZES_BTC = (5., 10., 20., 40., 60., 80.)


def experiment(params, seed=7, sizes=SIZES_BTC):
    flow = common_flow(params, seed)
    records = []
    for size in sizes:
        paired = {}
        for withdrawal in (False, True):
            rows, shock = run(params, flow, withdrawal, shock_qty=size)
            label = "withdrawal" if withdrawal else "normal"
            paired[label] = {"size_btc": size, "scenario": label,
                "immediate_mid_move_bps": shock["immediate_mid_move_bps"],
                "slippage_vs_pre_ask_bps": shock["slippage_vs_pre_ask_bps"],
                "pre_shock_mid": shock["pre_shock_mid"],
                "mid_at_shock": rows[SHOCK_SECOND + 1]["mid"],
                "mid_10s_later": rows[SHOCK_SECOND + 11]["mid"],
                "mid_30s_later": rows[SHOCK_SECOND + 31]["mid"],
                "spread_at_shock": rows[SHOCK_SECOND + 1]["spread"],
                "filled_btc": shock["filled_qty_btc"]}
        for label in ("normal", "withdrawal"):
            rec = paired[label]
            rec["incremental_move_vs_normal_bps"] = (
                rec["immediate_mid_move_bps"] - paired["normal"]["immediate_mid_move_bps"])
            records.append(rec)
    return records


def render(records, output):
    payload = json.dumps(records, separators=(",", ":")).replace("</", "<\\/")
    page = '''<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Market Ecology · Price impact</title>
<style>body{font:16px system-ui;background:#0b111a;color:#e5edf4;max-width:1100px;margin:28px auto;padding:0 18px}p{line-height:1.5;color:#b4c3d2}.panel{background:#172331;border:1px solid #34485a;border-radius:12px;padding:18px;margin:18px 0}canvas{width:100%;height:390px}table{border-collapse:collapse;width:100%;font-variant-numeric:tabular-nums}th,td{padding:9px;text-align:right;border-bottom:1px solid #34485a}th:first-child,td:first-child{text-align:left}.scroll{overflow:auto}small{color:#a3b2bf}.blue{color:#55b2e1}.orange{color:#f08a5a}</style>
<h1>Market Ecology · How much does price move?</h1><p>A controlled size sweep: the same background trades and initial book, with an aggressive buy of 5–80 BTC at second 120. <span class="blue">Blue: both makers</span>. <span class="orange">Maker B removes all displayed quotes and pauses 60 seconds</span>.</p>
<div class="panel"><canvas id="chart"></canvas><small>Vertical axis: immediate midprice move in basis points from that scenario's pre-buy mid. Horizontal axis: aggressive buy size in BTC. Lines join six separate simulations, not a fitted impact law.</small></div>
<div class="panel scroll"><table><thead><tr><th>Buy size BTC</th><th>Normal move bps</th><th>Withdrawal move bps</th><th>Extra move bps</th><th>Normal slippage bps</th><th>Withdrawal slippage bps</th></tr></thead><tbody id="rows"></tbody></table></div>
<p><strong>Mechanism:</strong> a buy consumes displayed asks from cheapest upward; fewer asks allow it to reach higher prices. Price here is the midpoint of the best remaining bid and ask. Execution slippage compares buy VWAP with the best ask just before that buy. The 60-second withdrawal also changes later replenishment.</p>
<p><strong>Boundary:</strong> these values are outputs of assumed agent behavior and a sample-scaled starting book, not measured real-world causal effects. Public book and trade data do not label a trade as retail, institutional or dealer hedging. There is no gamma flow, information, cross-venue arbitrage, fees, queue position or latency in this run.</p>
<script>const data=PAYLOAD;let groups={normal:data.filter(r=>r.scenario==='normal'),withdrawal:data.filter(r=>r.scenario==='withdrawal')};let f=x=>Number(x).toFixed(3);document.getElementById('rows').innerHTML=groups.normal.map((n,i)=>{let w=groups.withdrawal[i];return `<tr><td>${n.size_btc}</td><td>${f(n.immediate_mid_move_bps)}</td><td>${f(w.immediate_mid_move_bps)}</td><td>${f(w.incremental_move_vs_normal_bps)}</td><td>${f(n.slippage_vs_pre_ask_bps)}</td><td>${f(w.slippage_vs_pre_ask_bps)}</td></tr>`}).join('');function draw(){let el=document.getElementById('chart'),d=window.devicePixelRatio||1,w=el.clientWidth,h=el.clientHeight;el.width=w*d;el.height=h*d;let c=el.getContext('2d');c.scale(d,d);let left=60,right=20,top=24,bottom=43,all=data.map(r=>r.immediate_mid_move_bps),min=Math.min(0,...all),max=Math.max(...all),lo=min-(max-min||1)*.08,hi=max+(max-min||1)*.08,X=x=>left+(x-5)/75*(w-left-right),Y=y=>top+(hi-y)/(hi-lo)*(h-top-bottom);c.font='12px system-ui';for(let i=0;i<5;i++){let v=lo+(hi-lo)*i/4,y=Y(v);c.strokeStyle='#354959';c.beginPath();c.moveTo(left,y);c.lineTo(w-right,y);c.stroke();c.fillStyle='#b4c3d2';c.fillText(f(v),4,y+4)}for(let [name,color] of [['normal','#55b2e1'],['withdrawal','#f08a5a']]){c.strokeStyle=color;c.fillStyle=color;c.lineWidth=3;c.beginPath();groups[name].forEach((r,i)=>{let x=X(r.size_btc),y=Y(r.immediate_mid_move_bps);i?c.lineTo(x,y):c.moveTo(x,y)});c.stroke();groups[name].forEach(r=>{c.beginPath();c.arc(X(r.size_btc),Y(r.immediate_mid_move_bps),4,0,Math.PI*2);c.fill()})}c.fillStyle='#b4c3d2';groups.normal.forEach(r=>c.fillText(String(r.size_btc),X(r.size_btc)-8,h-13))}addEventListener('resize',draw);draw()</script></html>'''
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(page.replace('PAYLOAD', payload), encoding='utf-8')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config', type=Path, required=True)
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--seed', type=int, default=7)
    args = parser.parse_args()
    params = json.loads(args.config.read_text())['calibration_from_valid_samples']
    records = experiment(params, args.seed)
    args.out.mkdir(parents=True, exist_ok=True)
    with (args.out / 'impact_sweep.csv').open('w', newline='') as handle:
        writer = csv.DictWriter(handle, fieldnames=records[0].keys())
        writer.writeheader()
        writer.writerows(records)
    render(records, args.out / 'impact_sweep.html')
    print(json.dumps(records, indent=2))


if __name__ == '__main__':
    main()
