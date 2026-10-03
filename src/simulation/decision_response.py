"""Post-update receipt-time response; no future-path freshness selection."""
import argparse
import csv
import hashlib
import json
from pathlib import Path

from .flow_response import summarize, windows


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--raw-dir', type=Path, required=True)
    parser.add_argument('--states-dir', type=Path, required=True)
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)
    reports = []
    for changes in sorted(args.states_dir.glob('*_observed_changes.csv')):
        hour = changes.name.removeprefix('BTCUSDT_orderbook_').removesuffix('_observed_changes.csv')
        trades = args.raw_dir / f'BTCUSDT_trades_{hour}.parquet'
        report = dict(hour=hour, state='post_update_at_receipt',
            freshness='Known by flow-window end; future label ages never select the decision',
            sha256={p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in (changes, trades)})
        for name, age in [('all_messages', None), ('decision_fresh_250ms', 250.)]:
            rows = windows(changes, trades, age, state_mode='post', require_future_freshness=False)
            report[name] = summarize(rows, 1.)
            path = args.out / f'{hour}_{name}.csv'
            if rows:
                with path.open('w', newline='') as handle:
                    writer=csv.DictWriter(handle,fieldnames=rows[0]);writer.writeheader();writer.writerows(rows)
        reports.append(report)
        print(hour, json.dumps(report), flush=True)
    (args.out/'report.json').write_text(json.dumps(reports,indent=2)+'\n')


if __name__ == '__main__':
    main()
