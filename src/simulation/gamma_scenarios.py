"""Illustrative dealer-gamma hedge scenarios, with no options data fitted.

Run: python -m src.simulation.gamma_scenarios --config configs/simulation_v1_demo.json --out data/processed/gamma_scenarios
"""
import argparse
import csv
import json
from pathlib import Path

from .ecology import SHOCK_SECOND, common_flow, run

SHOCK_BTC = 60.
GAMMA_CASES = (("long_gamma", .5), ("neutral", 0.), ("short_gamma", -.5))


def experiment(params, seed=7):
    flow = common_flow(params, seed)
    summary, trajectories = [], []
    for withdrawal in (False, True):
        for label, signed_gamma in GAMMA_CASES:
            rows, shock = run(params, flow, withdrawal, shock_qty=SHOCK_BTC,
                              dealer_gamma_btc_per_usdt=signed_gamma)
            scenario = "maker_withdrawal" if withdrawal else "normal_liquidity"
            summary.append({"liquidity": scenario, "gamma_case": label,
                            "assumed_gamma_btc_per_usdt": signed_gamma,
                            "initiating_buy_btc": SHOCK_BTC,
                            "hedge_side": shock["hedge_side"],
                            "hedge_requested_btc": shock["hedge_requested_btc"],
                            "hedge_filled_btc": shock["hedge_filled_btc"],
                            "move_after_initiating_buy_bps":
                                (shock["mid_after_initiating_buy"] / shock["pre_shock_mid"] - 1) * 10_000,
                            "move_after_hedge_bps": shock["immediate_mid_move_bps"],
                            "spread_after_hedge_usdt": shock["immediate_spread"]})
            for row in rows:
                if 110 <= row["second"] <= 180:
                    trajectories.append({"liquidity": scenario, "gamma_case": label,
                                         "second": row["second"],
                                         "mid_move_bps_from_pre_buy":
                                             (row["mid"] / shock["pre_shock_mid"] - 1) * 10_000})
    return summary, trajectories


def render(summary, trajectories, path):
    data = json.dumps({"summary": summary, "trajectories": trajectories}, separators=(",", ":")).replace("</", "<\\/")
    page = '''<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Market Ecology · Hypothetical gamma hedges</title><style>body{font:16px system-ui;background:#0b111a;color:#e4edf4;max-width:1100px;margin:28px auto;padding:0 18px}p{line-height:1.5;color:#b4c3d2}.panel{background:#172331;border:1px solid #34485a;border-radius:12px;padding:18px;margin:18px 0}canvas{width:100%;height:400px}table{border-collapse:collapse;width:100%;font-variant-numeric:tabular-nums}th,td{padding:9px;text-align:right;border-bottom:1px solid #34485a}th:first-child,td:first-child{text-align:left}.scroll{overflow:auto}select{background:#263749;color:white;padding:7px;border:1px solid #587084;border-radius:6px}.key{display:flex;gap:20px;flex-wrap:wrap;color:#bbcbd7}.key span{border-left:5px solid;padding-left:8px}</style><h1>Market Ecology · What might gamma hedging do to price?</h1><p>A <strong>hypothetical</strong> dealer sees the midpoint move after a 60 BTC initiating buy at second 120, then sends one hedge order. The same background trades run in all cases. Choose whether both makers are quoting or maker B withdraws.</p><div class="panel"><label>Liquidity: <select id="liquidity"><option value="normal_liquidity">Both makers</option><option value="maker_withdrawal">Maker B withdraws</option></select></label><canvas id="chart"></canvas><div class="key"><span style="border-color:#60bcd9">Long gamma: sell after rise</span><span style="border-color:#e8cc73">Neutral: no hedge</span><span style="border-color:#f08a5a">Short gamma: buy after rise</span></div><p>Price is the midpoint in basis points relative to that scenario's pre-buy midpoint. The displayed jump at second 120 includes the initiating buy and then one dealer hedge. Later paths also include ongoing background flow and maker replenishment.</p></div><div class="panel scroll"><table><thead><tr><th>Liquidity / dealer case</th><th>Hedge</th><th>BTC filled</th><th>Move after initiating buy (bps)</th><th>Move after hedge (bps)</th></tr></thead><tbody id="table"></tbody></table></div><p><strong>Assumptions:</strong> long/short gamma ±0.5 BTC per $1 move, instant one-round hedge, 60 BTC initiating buy. There is no observed dealer position, options chain, hedge timing estimate, cross-venue route or calibrated fill model. A visible price difference here is a model result, not evidence that dealers caused a historical move.</p><script>const payload=PAYLOAD;const colors={long_gamma:'#60bcd9',neutral:'#e8cc73',short_gamma:'#f08a5a'},names={long_gamma:'Long gamma',neutral:'Neutral',short_gamma:'Short gamma'};let select=document.getElementById('liquidity');function fmt(x){return Number(x).toFixed(3)}function draw(){let kind=select.value,rows=payload.summary.filter(r=>r.liquidity===kind);document.getElementById('table').innerHTML=rows.map(r=>`<tr><td>${r.liquidity==='normal_liquidity'?'Both makers':'Maker B withdraws'} / ${names[r.gamma_case]}</td><td>${r.hedge_side}</td><td>${fmt(r.hedge_filled_btc)}</td><td>${fmt(r.move_after_initiating_buy_bps)}</td><td>${fmt(r.move_after_hedge_bps)}</td></tr>`).join('');let canvas=document.getElementById('chart'),scale=window.devicePixelRatio||1,w=canvas.clientWidth,h=canvas.clientHeight;canvas.width=w*scale;canvas.height=h*scale;let c=canvas.getContext('2d');c.scale(scale,scale);let series=payload.trajectories.filter(r=>r.liquidity===kind),values=series.map(r=>r.mid_move_bps_from_pre_buy),min=Math.min(...values),max=Math.max(...values),pad=(max-min||1)*.1,lo=min-pad,hi=max+pad,L=64,R=18,T=20,B=40,X=s=>L+(s-110)/70*(w-L-R),Y=v=>T+(hi-v)/(hi-lo)*(h-T-B);c.font='12px system-ui';for(let i=0;i<5;i++){let v=lo+(hi-lo)*i/4,y=Y(v);c.strokeStyle='#34495a';c.beginPath();c.moveTo(L,y);c.lineTo(w-R,y);c.stroke();c.fillStyle='#bac9d5';c.fillText(fmt(v),4,y+4)}for(let name of Object.keys(colors)){c.beginPath();c.strokeStyle=colors[name];c.lineWidth=2;series.filter(r=>r.gamma_case===name).forEach((r,i)=>{let x=X(r.second),y=Y(r.mid_move_bps_from_pre_buy);i?c.lineTo(x,y):c.moveTo(x,y)});c.stroke()}c.setLineDash([5,5]);c.strokeStyle='#d0dbe4';c.beginPath();c.moveTo(X(120),T);c.lineTo(X(120),h-B);c.stroke();c.setLineDash([]);c.fillStyle='#bac9d5';for(let s of [110,120,130,140,150,160,170,180])c.fillText(String(s),X(s)-10,h-10)}select.addEventListener('change',draw);addEventListener('resize',draw);draw()</script></html>'''
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(page.replace('PAYLOAD', data), encoding='utf-8')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config', type=Path, required=True)
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--seed', type=int, default=7)
    args = parser.parse_args()
    params = json.loads(args.config.read_text())['calibration_from_valid_samples']
    summary, trajectories = experiment(params, args.seed)
    args.out.mkdir(parents=True, exist_ok=True)
    for filename, records in [('gamma_scenarios.csv', summary), ('gamma_trajectories.csv', trajectories)]:
        with (args.out / filename).open('w', newline='') as handle:
            writer = csv.DictWriter(handle, fieldnames=records[0].keys())
            writer.writeheader()
            writer.writerows(records)
    render(summary, trajectories, args.out / 'gamma_scenarios.html')
    print(json.dumps(summary, indent=2))


if __name__ == '__main__':
    main()
