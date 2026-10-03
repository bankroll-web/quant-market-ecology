"""Verify saved-tokenizer inference against delivered forecasts on both later hours."""
import argparse
import hashlib
import importlib.metadata
import json
from pathlib import Path
import platform
import numpy as np
import pandas as pd
from receipt_predict import ReceiptPredictor
from receipt_tokens import load_receipt_hours
from train_real import L, QS

def run(repo, upload):
    root = Path(repo)
    out = root/'docs/market_tokens/receipt_trial'
    audit = json.loads((out/'RUN_AUDIT.json').read_text())
    for name, digest in audit['artifacts_sha256'].items():
        if hashlib.sha256((out/name).read_bytes()).hexdigest() != digest:
            raise AssertionError('Artifact hash changed: '+name)
    results = json.loads((out/'RESULTS.json').read_text())
    for name, digest in results['code_sha256'].items():
        if hashlib.sha256((root/name).read_bytes()).hexdigest() != digest:
            raise AssertionError('Training code hash changed: '+name)
    predictor = ReceiptPredictor(out)
    hours, _ = load_receipt_hours(root, upload)
    pred = pd.read_csv(out/'PREDICTIONS.csv.gz')
    checks = []
    for df in hours[3:]:
        hour = df['hour'].iloc[0]
        row = pred.loc[pred['hour'] == hour].iloc[0]
        j = np.flatnonzero(df['decision_receipt_ns'].to_numpy() == int(row['decision_receipt_ns']))
        if len(j) != 1:
            raise AssertionError('Receipt decision must uniquely identify this checked row')
        context = df.iloc[j[0]-L+1:j[0]+1].copy()
        result = predictor.predict(context)
        expected = [row['return_q'+str(q)] for q in QS]+[row['predicted_flow'], row['predicted_vol']]
        observed = list(result['return_quantiles_bps'].values())+[result['flow_forecast'], result['vol_forecast_bps']]
        error = float(np.max(np.abs(np.asarray(expected)-observed)))
        if error > 1e-6:
            raise AssertionError('Frozen tokenizer/model forecast differs from delivered forecast')
        context.loc[context.index[-1], 'receipt_valid'] = False
        try:
            predictor.predict(context)
        except ValueError:
            pass
        else:
            raise AssertionError('Invalid context was not rejected')
        checks.append({'hour': hour, 'max_absolute_forecast_difference': error,
                       'invalid_context_rejected': True})
    record = {
        'checks': checks, 'trained_artifact_and_code_hashes_verified': True,
        'inference_code_sha256': hashlib.sha256((root/'receipt_predict.py').read_bytes()).hexdigest(),
        'python': platform.python_version(),
        'packages': {name: importlib.metadata.version(name) for name in ('numpy', 'pandas', 'torch', 'pyarrow', 'zstandard')},
        'example_note': 'EXAMPLE_FORECAST is a historical replay sample, not a current market signal.',
    }
    (out/'INFERENCE_AUDIT.json').write_text(json.dumps(record, indent=2)+'\n')
    print(json.dumps(record, indent=2))
    return record

if __name__ == '__main__':
    p = argparse.ArgumentParser()
    p.add_argument('--repo', default='.')
    p.add_argument('--upload', required=True)
    args = p.parse_args()
    run(args.repo, args.upload)
