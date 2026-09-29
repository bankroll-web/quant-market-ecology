"""One-second observed signed-flow/price-response diagnostic inside valid book episodes.

Associational, not a causal impact or participant-identification estimator.
"""
import argparse
import csv
import json
import math
from pathlib import Path

import pyarrow.parquet as pq

from .book_changes import plain

NS = 1_000_000_000
MAX_SAMPLING_LAG_NS = 250_000_000
HORIZONS = (1, 5)


def trade_tape(path):
    source, temporary = plain(path)
    trades = []
    try:
        for batch in pq.ParquetFile(source).iter_batches(
                batch_size=100_000, columns=['received_time', 'quantity', 'is_buyer_maker', 'trade_time']):
            data = batch.to_pydict()
            trades.extend((int(t), float(q) * (-1 if maker else 1),
                           (int(t) - int(exchange_t) * 1_000_000) / 1_000_000)
                          for t, q, maker, exchange_t in zip(data['received_time'], data['quantity'],
                                                 data['is_buyer_maker'], data['trade_time']))
    finally:
        if temporary:
            Path(temporary).unlink()
    trades.sort()
    return trades


def windows(changes_csv, trades_path, max_message_age_ms=None):
    with open(changes_csv, newline='') as handle:
        book = list(csv.DictReader(handle))
    trades = trade_tape(trades_path)
    times = [int(r['received_time_ns']) for r in book]
    if any(b < a for a, b in zip(times, times[1:])):
        raise ValueError('Nonmonotonic book receipt time')
    output, next_start, trade_index, n = [], 0, 0, len(book)
    for i, start in enumerate(book):
        # Nonoverlapping windows per episode: the next start is at or beyond
        # the preceding end, so the same trade is never counted twice.
        if i < next_start:
            continue
        episode = start['episode']
        t0 = int(start['received_time_ns'])
        end = i + 1
        while end < n and book[end]['episode'] == episode and int(book[end]['received_time_ns']) < t0 + NS:
            end += 1
        if end == n or book[end]['episode'] != episode:
            continue
        t1 = int(book[end]['received_time_ns'])
        if t1 - t0 - NS > MAX_SAMPLING_LAG_NS:
            continue
        # The next valid pre-update book midpoint is the end-of-window price.
        first = trade_index
        while first < len(trades) and trades[first][0] < t0:
            first += 1
        last = first
        buy = sell = 0.
        while last < len(trades) and trades[last][0] < t1:
            qty = trades[last][1]
            if qty > 0: buy += qty
            else: sell -= qty
            last += 1
        trade_index = last
        next_start = end
        def fresh_book(a, b):
            if max_message_age_ms is None:
                return True
            return all(0 <= (int(r['received_time_ns']) - int(r['event_time_ms']) * 1_000_000) / 1_000_000 <= max_message_age_ms
                       for r in book[a:b + 1])
        if not fresh_book(i, end) or (max_message_age_ms is not None and
                any(not 0 <= t[2] <= max_message_age_ms for t in trades[first:last])):
            continue
        p0 = float(start['pre_mid'])
        p1 = float(book[end]['pre_mid'])
        row = {'start_received_ns': t0, 'end_received_ns': t1, 'episode': episode,
                       'duration_seconds': (t1 - t0) / NS,
                       'buy_btc': buy, 'sell_btc': sell, 'signed_btc': buy - sell,
                       'absolute_trade_btc': buy + sell,
                       'mid_log_return_bps': 10_000 * math.log(p1 / p0),
                       'start_mid': p0, 'end_mid': p1}
        for horizon in HORIZONS:
            target = t1 + horizon * NS
            future = end + 1
            while future < n and book[future]['episode'] == episode and times[future] < target:
                future += 1
            key = f'forward_{horizon}s_return_bps'
            row[key] = None
            if (future < n and book[future]['episode'] == episode and
                    times[future] - target <= MAX_SAMPLING_LAG_NS and fresh_book(end, future)):
                row[key] = 10_000 * math.log(float(book[future]['pre_mid']) / p1)
        output.append(row)
    return output


def summarize(rows, threshold_btc):
    eligible = [r for r in rows if abs(r['signed_btc']) >= threshold_btc]
    aligned = [r['mid_log_return_bps'] * (1 if r['signed_btc'] > 0 else -1) for r in eligible
               if r['signed_btc'] != 0]
    result = {'windows': len(rows), 'nonzero_flow_windows': sum(r['absolute_trade_btc'] > 0 for r in rows),
            'large_signed_flow_threshold_btc': threshold_btc,
            'eligible_windows': len(eligible),
            'mean_direction_aligned_return_bps': sum(aligned) / len(aligned) if aligned else None,
            'fraction_zero_mid_return': sum(v == 0 for v in aligned) / len(aligned) if aligned else None,
            'fraction_direction_aligned_positive_including_zeros': sum(v > 0 for v in aligned) / len(aligned) if aligned else None,
            'note': 'Same-window association, not causal market impact; window coverage requires a verified book episode.'}
    for horizon in HORIZONS:
        values = [r[f'forward_{horizon}s_return_bps'] * (1 if r['signed_btc'] > 0 else -1)
                  for r in eligible if r.get(f'forward_{horizon}s_return_bps') is not None]
        result[f'forward_{horizon}s_eligible_windows'] = len(values)
        result[f'forward_{horizon}s_mean_direction_aligned_return_bps'] = sum(values) / len(values) if values else None
    return result


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--changes', required=True, type=Path)
    p.add_argument('--trades', required=True, type=Path)
    p.add_argument('--out', required=True, type=Path)
    p.add_argument('--threshold-btc', type=float, default=1.)
    p.add_argument('--max-message-age-ms', type=float, default=None,
                   help='Sensitivity filter: reject windows containing older book/trade messages')
    args = p.parse_args()
    if args.threshold_btc <= 0: p.error('threshold must be positive')
    rows = windows(args.changes, args.trades, args.max_message_age_ms)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    with args.out.open('w', newline='') as handle:
        if rows:
            writer = csv.DictWriter(handle, fieldnames=rows[0])
            writer.writeheader()
            writer.writerows(rows)
    print(json.dumps(summarize(rows, args.threshold_btc), indent=2))


if __name__ == '__main__':
    main()
