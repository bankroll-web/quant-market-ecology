"""Reproduce the four-hour receipt-time flow-response sensitivity study."""
import argparse
import csv
import hashlib
import json
from pathlib import Path

import pyarrow.parquet as pq
from .book_changes import plain
from .flow_response import summarize, windows

HOURS = ('2026-05-25_12', '2026-05-25_18', '2026-05-26_15', '2026-05-26_21')


def quantiles(values):
    values = sorted(values)
    return {name: values[int(q * (len(values) - 1))]
            for name, q in [('p05_ms', .05), ('median_ms', .5), ('p95_ms', .95)]}


def clock_audit(changes, trades):
    with changes.open() as handle:
        book = list(csv.DictReader(handle))
    book_age = [(int(r['received_time_ns']) - int(r['event_time_ms']) * 1_000_000) / 1_000_000 for r in book]
    path, temporary = plain(trades)
    try:
        data = pq.read_table(path, columns=['received_time', 'trade_time', 'trade_id']).to_pydict()
    finally:
        if temporary: Path(temporary).unlink()
    trade_age = [(int(t) - int(e) * 1_000_000) / 1_000_000
                 for t, e in zip(data['received_time'], data['trade_time'])]
    return {'book_receipt_minus_event': quantiles(book_age),
            'trade_receipt_minus_trade': quantiles(trade_age),
            'negative_book_age_count': sum(v < 0 for v in book_age),
            'negative_trade_age_count': sum(v < 0 for v in trade_age),
            'trade_rows': len(trade_age),
            'duplicate_trade_ids': len(data['trade_id']) - len(set(data['trade_id']))}


def render(reports, path):
    payload = json.dumps(reports, separators=(',', ':')).replace('</', '<\\/')
    page = '''<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Real BTC data · Flow and price</title><style>body{font:16px system-ui;background:#0b111a;color:#e4edf4;max-width:1100px;margin:28px auto;padding:0 18px}p{line-height:1.5;color:#b4c3d2}.panel{background:#172331;border:1px solid #34485a;border-radius:12px;padding:18px;margin:18px 0}canvas{width:100%;height:370px}table{border-collapse:collapse;width:100%;font-variant-numeric:tabular-nums}th,td{padding:9px;text-align:right;border-bottom:1px solid #34485a}th:first-child,td:first-child{text-align:left}.scroll{overflow:auto}select{background:#263749;color:white;padding:7px;border:1px solid #587084;border-radius:6px}</style><h1>What did real price do around buying and selling pressure?</h1><p>We inspect approximately one-second windows where buyers took at least 1 BTC more than sellers, or sellers took at least 1 BTC more than buyers. Positive values mean price moved in the direction of that net pressure; negative values mean it moved against it.</p><div class="panel"><label>Measure <select id="measure"><option value="during">During the flow window</option><option value="forward1">Next 1 second after the window</option><option value="forward5">Next 5 seconds after the window</option></select></label><canvas id="chart"></canvas><p>Blue: all eligible messages. Orange: reject windows containing book or trade messages older than 250 ms. Different filters and horizons retain different samples; compare counts below.</p></div><div class="panel scroll"><table><thead><tr><th>UTC hour</th><th>All: windows</th><th>All: mean bps</th><th>Fresh: windows</th><th>Fresh: mean bps</th></tr></thead><tbody id="rows"></tbody></table></div><p><strong>Read this carefully:</strong> price moving alongside flow does not show that the flow caused it or that you can predict the next move. Late messages, changing liquidity and shared news can affect both. The 250 ms filter is an exploratory sensitivity check, chosen after inspecting message ages; it selects quieter/fresher periods. Forward horizons overlap and 5-second fresh samples are very small. These are four selected hours across two days, not independent validation of a strategy.</p><script>const reports=PAYLOAD;let select=document.getElementById('measure');function pair(r,mode){let s=r[mode],m=select.value;if(m==='during')return[s.eligible_windows,s.mean_direction_aligned_return_bps];let h=m==='forward1'?1:5;return[s['forward_'+h+'s_eligible_windows'],s['forward_'+h+'s_mean_direction_aligned_return_bps']]}function fmt(x){return x===null?'—':Number(x).toFixed(3)}function draw(){document.getElementById('rows').innerHTML=reports.map(r=>{let a=pair(r,'all_messages'),f=pair(r,'fresh_250ms');return `<tr><td>${r.hour.replace('_',' ')}</td><td>${a[0]}</td><td>${fmt(a[1])}</td><td>${f[0]}</td><td>${fmt(f[1])}</td></tr>`}).join('');let el=document.getElementById('chart'),d=window.devicePixelRatio||1,w=el.clientWidth,h=el.clientHeight;el.width=w*d;el.height=h*d;let c=el.getContext('2d');c.scale(d,d);let v=reports.flatMap(r=>[pair(r,'all_messages')[1],pair(r,'fresh_250ms')[1]]).filter(x=>x!==null),lo=Math.min(0,...v)-.04,hi=Math.max(0,...v)+.04,L=65,R=15,T=20,B=45,Y=x=>T+(hi-x)/(hi-lo)*(h-T-B),step=(w-L-R)/4;c.font='12px system-ui';for(let i=0;i<5;i++){let x=lo+(hi-lo)*i/4,y=Y(x);c.strokeStyle='#34495a';c.beginPath();c.moveTo(L,y);c.lineTo(w-R,y);c.stroke();c.fillStyle='#b4c3d2';c.fillText(fmt(x),4,y+4)}reports.forEach((r,i)=>{let center=L+step*(i+.5),bar=Math.min(28,step*.23);for(let [j,mode,color] of [[0,'all_messages','#60bcd9'],[1,'fresh_250ms','#f08a5a']]){let x=pair(r,mode)[1];if(x!==null){c.fillStyle=color;c.fillRect(center+(j-1)*bar,Y(Math.max(0,x)),bar-2,Math.max(1,Math.abs(Y(x)-Y(0))))}}c.fillStyle='#b4c3d2';c.fillText(r.hour.slice(8).replace('_',' / ')+' UTC',center-37,h-12)})}select.addEventListener('change',draw);addEventListener('resize',draw);draw()</script></html>'''
    path.write_text(page.replace('PAYLOAD', payload), encoding='utf-8')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--changes-dir', type=Path, required=True)
    parser.add_argument('--raw-dir', type=Path, required=True)
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)
    reports = []
    for hour in HOURS:
        changes = args.changes_dir / f'BTCUSDT_orderbook_{hour}_observed_changes.csv'
        trades = args.raw_dir / f'BTCUSDT_trades_{hour}.parquet'
        report = {'hour': hour, 'trades_sha256': hashlib.sha256(trades.read_bytes()).hexdigest(),
                  'changes_csv_sha256': hashlib.sha256(changes.read_bytes()).hexdigest(),
                  **clock_audit(changes, trades)}
        for name, age in [('all_messages', None), ('fresh_250ms', 250.)]:
            records = windows(changes, trades, age)
            report[name] = summarize(records, 1.)
            with (args.out / f'{hour}_{name}.csv').open('w', newline='') as handle:
                if records:
                    writer = csv.DictWriter(handle, fieldnames=records[0]); writer.writeheader(); writer.writerows(records)
        reports.append(report)
    (args.out / 'report.json').write_text(json.dumps(reports, indent=2) + '\n')
    render(reports, args.out / 'real_flow_price.html')
    print(json.dumps(reports, indent=2))


if __name__ == '__main__':
    main()
