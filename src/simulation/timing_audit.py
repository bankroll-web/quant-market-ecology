"""Receipt/event ordering and post-update availability audit on supplied hours."""
import argparse
import csv
import hashlib
import json
from pathlib import Path

import numpy as np
import pyarrow.parquet as pq

from .book_changes import plain


def timing(receipts, exchange_ms):
    if not receipts:
        return {'messages': 0}
    age = (np.asarray(receipts, dtype=np.int64) - np.asarray(exchange_ms, dtype=np.int64) * 1_000_000) / 1_000_000
    cadence = np.diff(np.sort(np.unique(receipts))) / 1_000_000
    return dict(messages=len(receipts), negative_age_count=int(np.sum(age < 0)),
        age_median_ms=float(np.median(age)), age_p95_ms=float(np.quantile(age, .95)),
        age_max_ms=float(np.max(age)), age_over_250ms_pct=float(np.mean(age > 250) * 100),
        receipt_backsteps_in_file=int(np.sum(np.diff(receipts) < 0)),
        exchange_backsteps_in_file=int(np.sum(np.diff(exchange_ms) < 0)),
        duplicate_receipt_timestamps=len(receipts) - len(set(receipts)),
        distinct_receipt_cadence_median_ms=float(np.median(cadence)) if len(cadence) else None,
        distinct_receipt_cadence_p95_ms=float(np.quantile(cadence, .95)) if len(cadence) else None)


def raw_clock(path, book=False):
    source, temporary = plain(path)
    try:
        columns = (['received_time', 'event_time', 'transaction_time', 'event_type',
                    'first_update_id', 'final_update_id', 'prev_final_update_id', 'last_update_id']
                   if book else ['received_time', 'trade_time', 'trade_id'])
        seen, receipts, exchange, transactions, identifiers = set(), [], [], [], []
        raw_rows = 0
        for batch in pq.ParquetFile(source).iter_batches(batch_size=100000, columns=columns):
            data = batch.to_pydict()
            for row in zip(*(data[name] for name in columns)):
                raw_rows += 1
                if book:
                    r, e, tx, kind, first, final, previous, last = row
                    # One message expands into many L2 price-level rows.
                    key = (r, e, tx, kind, first, final, previous, last)
                    if key in seen:
                        continue
                    seen.add(key)
                    if kind != 'update':
                        continue
                    transactions.append(int(tx))
                else:
                    r, e, identifier = row
                    identifiers.append(identifier)
                receipts.append(int(r)); exchange.append(int(e))
        result = dict(raw_rows=raw_rows, **timing(receipts, exchange))
        if book:
            result['event_minus_transaction_median_ms'] = float(np.median(np.asarray(exchange) - transactions)) if transactions else None
        else:
            result['duplicate_trade_ids'] = len(identifiers) - len(set(identifiers))
        return result
    finally:
        if temporary:
            Path(temporary).unlink()


def boundary(changes):
    with Path(changes).open(newline='') as handle:
        rows = list(csv.DictReader(handle))
    mismatches, comparisons, gaps = 0, 0, []
    for previous, current in zip(rows, rows[1:]):
        if current['episode'] != previous['episode']:
            continue
        comparisons += 1
        if abs(float(previous['post_mid']) - float(current['pre_mid'])) > 1e-8:
            mismatches += 1
        gaps.append((int(current['received_time_ns']) - int(previous['received_time_ns'])) / 1_000_000)
    return dict(emitted_intervals=len(rows), post_to_next_pre_comparisons=comparisons,
        post_to_next_pre_mid_mismatches=mismatches,
        pre_state_label_age_median_ms=float(np.median(gaps)) if gaps else None,
        pre_state_label_age_p95_ms=float(np.quantile(gaps, .95)) if gaps else None,
        verified_exposure_seconds=sum(float(r['exposure_seconds']) for r in rows),
        rows_with_duplicate_receipt=len(rows)-len({r['received_time_ns'] for r in rows}),
        conclusion='Use post-update state at its receipt time. Pre-update states describe the preceding state; future-path freshness is not an online selection rule.')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--raw-dir', type=Path, required=True)
    parser.add_argument('--states-dir', type=Path, required=True)
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    reports = []
    for changes in sorted(args.states_dir.glob('*_observed_changes.csv')):
        hour = changes.name.removeprefix('BTCUSDT_orderbook_').removesuffix('_observed_changes.csv')
        candidates = list(args.raw_dir.glob(f'BTCUSDT_orderbook_{hour}*.parquet'))
        if len(candidates) != 1:
            raise ValueError(f'Expected one raw book file for {hour}, found {len(candidates)}')
        book = candidates[0]
        trades = args.raw_dir / f'BTCUSDT_trades_{hour}.parquet'
        report = dict(hour=hour, book=raw_clock(book, True), trades=raw_clock(trades),
            observation_boundary=boundary(changes),
            sha256={p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in (book, trades, changes)})
        reports.append(report)
        print(hour, json.dumps(report), flush=True)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(reports, indent=2)+'\n')


if __name__ == '__main__':
    main()
