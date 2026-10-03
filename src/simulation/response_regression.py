"""Fixed chronological ridge baseline on receipt-time flow diagnostics.

Research predictions of midpoint returns, not executable trade returns.
"""
import argparse
import csv
import hashlib
import json
import math
from pathlib import Path

import numpy as np

HOURS = ('2026-05-25_12', '2026-05-25_18', '2026-05-26_15', '2026-05-26_21')
FEATURES = ('net_flow_over_start_depth', 'start_top_obi', 'log1p_total_flow')
TARGET = 'forward_1s_return_bps'
ALPHA = 1.0
NS = 1_000_000_000


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def samples(flow_path, changes_path):
    # Exact receipt timestamp AND episode join; never use a future book state.
    with Path(changes_path).open(newline='') as handle:
        book = {(r['received_time_ns'], r['episode']): r for r in csv.DictReader(handle)}
    with Path(flow_path).open(newline='') as handle:
        flow = list(csv.DictReader(handle))
    flow.sort(key=lambda r: int(r['start_received_ns']))
    result = []
    available = -1
    for row in flow:
        start = int(row['start_received_ns'])
        if start < available or not row[TARGET]:
            continue
        state = book.get((str(start), row['episode']))
        if state is None:
            raise ValueError('Flow window has no exact initial book state')
        depth = float(state['pre_bid_depth_10bps']) + float(state['pre_ask_depth_10bps'])
        if depth <= 0:
            continue
        features = [float(row['signed_btc']) / depth,
                    float(state['pre_obi_top']), math.log1p(float(row['absolute_trade_btc']))]
        target = float(row[TARGET])
        if not all(math.isfinite(v) for v in features + [target]):
            raise ValueError('Nonfinite input')
        result.append(dict(start_ns=start, end_ns=int(row['end_received_ns']),
                           x=features, y=target))
        # Actual horizon endpoint is <= end + 1s + 250ms. A conservative
        # embargo keeps the next feature window out of that label interval.
        available = int(row['end_received_ns']) + 1_250_000_000
    return result


def fit(rows):
    if len(rows) < len(FEATURES) + 2:
        raise ValueError('Insufficient training rows')
    x = np.asarray([r['x'] for r in rows], dtype=float)
    y = np.asarray([r['y'] for r in rows], dtype=float)
    center, scale = x.mean(axis=0), x.std(axis=0)
    scale[scale == 0] = 1
    z = (x - center) / scale
    intercept = float(y.mean())
    weights = np.linalg.solve(z.T @ z + ALPHA * np.eye(x.shape[1]), z.T @ (y - intercept))
    return dict(feature_names=list(FEATURES), center=center.tolist(), scale=scale.tolist(),
                standardized_weights=weights.tolist(), intercept_bps=intercept, alpha=ALPHA)


def predict(model, rows):
    if not rows:
        return np.asarray([])
    x = np.asarray([r['x'] for r in rows])
    return model['intercept_bps'] + ((x - model['center']) / model['scale']) @ np.asarray(model['standardized_weights'])


def evaluate(model, rows):
    if not rows:
        return dict(rows=0, rmse_bps=None, zero_rmse_bps=None,
                    training_mean_rmse_bps=None, improvement_vs_zero_pct=None)
    y = np.asarray([r['y'] for r in rows])
    rmse = float(np.sqrt(np.mean((y - predict(model, rows)) ** 2)))
    zero = float(np.sqrt(np.mean(y ** 2)))
    mean = float(np.sqrt(np.mean((y - model['intercept_bps']) ** 2)))
    return dict(rows=len(rows), rmse_bps=rmse, zero_rmse_bps=zero,
                training_mean_rmse_bps=mean,
                improvement_vs_zero_pct=100 * (1 - rmse / zero) if zero else None)


def run(flow_dir, changes_dir, out):
    results = dict(target=TARGET, feature_names=list(FEATURES), alpha=ALPHA,
                   train_hour=HOURS[0], evaluation_hours=list(HOURS[1:]),
                   label_embargo_ns=1_250_000_000, samples={})
    predictions = []
    for sample in ('all_messages', 'fresh_250ms'):
        datasets, provenance = {}, {}
        for hour in HOURS:
            flow = Path(flow_dir) / f'{hour}_{sample}.csv'
            changes = Path(changes_dir) / f'BTCUSDT_orderbook_{hour}_observed_changes.csv'
            datasets[hour] = samples(flow, changes)
            provenance[hour] = dict(flow_sha256=digest(flow), changes_sha256=digest(changes))
        model = fit(datasets[HOURS[0]])
        results['samples'][sample] = dict(model=model, provenance=provenance,
            scores={hour: dict(role='training' if hour == HOURS[0] else 'held_out',
                              **evaluate(model, rows)) for hour, rows in datasets.items()})
        for hour, rows in datasets.items():
            for row, pred in zip(rows, predict(model, rows)):
                predictions.append(dict(sample=sample, hour=hour,
                    role='training' if hour == HOURS[0] else 'held_out',
                    start_received_ns=row['start_ns'], end_received_ns=row['end_ns'],
                    observed_bps=row['y'], predicted_bps=float(pred)))
    out = Path(out)
    out.mkdir(parents=True, exist_ok=True)
    (out / 'report.json').write_text(json.dumps(results, indent=2) + '\n')
    with (out / 'predictions.csv').open('w', newline='') as handle:
        writer = csv.DictWriter(handle, fieldnames=predictions[0])
        writer.writeheader()
        writer.writerows(predictions)
    return results


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--flow-dir', type=Path, required=True)
    parser.add_argument('--changes-dir', type=Path, required=True)
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(run(args.flow_dir, args.changes_dir, args.out), indent=2))
