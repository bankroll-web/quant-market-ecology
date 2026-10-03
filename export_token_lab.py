"""Export a standalone visual lab from the measured receipt-token experiment."""
import argparse
import hashlib
import json
from pathlib import Path
import numpy as np
import pandas as pd
from receipt_tokens import load_receipt_hours
from receipt_predict import ReceiptPredictor
from tokenizer_v1 import features

LABELS = ['Receipt gap · ms', 'Trade count', 'Signed flow · BTC', 'Bid added · BTC',
          'Bid removed · BTC', 'Ask added · BTC', 'Ask removed · BTC',
          'Deep bid net · BTC', 'Deep ask net · BTC', 'Mid move · rounded ticks',
          'Book imbalance', 'Wide spread flag']

def export(repo, upload):
    root = Path(repo)
    trial = root/'docs/market_tokens/receipt_trial'
    model = ReceiptPredictor(trial)
    hours, _ = load_receipt_hours(root, upload)
    predictions = pd.read_csv(trial/'PREDICTIONS.csv.gz')
    result = json.loads((trial/'RESULTS.json').read_text())
    recordings = []
    for df in hours[3:]:
        hour = df['hour'].iloc[0]
        df['episode_id'] = hour+'_'+df['episode_id'].astype(str)
        p = predictions.loc[predictions['hour'] == hour]
        step = max(1, int(np.ceil(len(p)/350)))
        selected = pd.concat([p.iloc[::step], p.iloc[-1:]]).drop_duplicates('decision_receipt_ns')
        lookup = {(ep, int(ns)): i for i, (ep, ns) in enumerate(zip(df['episode_id'], df['decision_receipt_ns']))}
        rows = []
        for _, row in selected.iterrows():
            j = lookup[(row['episode_id'], int(row['decision_receipt_ns']))]
            context = df.iloc[j-15:j+1]
            # Verify a legitimate observed context before exporting its frozen IDs.
            forecast = model.predict(context)
            tokens, _ = model.tokenizer.transform(context)
            numeric = features(context).iloc[-1].to_numpy(dtype=float)
            decoded = {name: float(b.inverse([tokens[name].iloc[-1]])[0])
                       for name, b in model.tokenizer.b.items() if hasattr(b, 'inverse')}
            rows.append({
                't': int(row['decision_receipt_ns'])//10**6,
                'target_t': int(row['target_receipt_ns'])//10**6,
                'receipt_ns': str(int(row['decision_receipt_ns'])),
                'mid': float(row['anchor_mid']), 'target_mid': float(row['target_mid']),
                'return_bps': float(row['return_bps']),
                'q': [float(row['return_q'+str(q)]) for q in (.1,.25,.5,.75,.9)],
                'flow': float(row['predicted_flow']), 'vol': float(row['predicted_vol']),
                'actual_flow': None if pd.isna(row['future_flow']) else float(row['future_flow']),
                'actual_vol': float(row['future_vol']),
                'tokens': tokens.values.tolist(), 'raw': numeric.tolist(), 'decoded': decoded,
                'episode': str(row['episode_id']),
            })
            if abs(forecast['return_quantiles_bps']['0.5']-row['return_q0.5']) > 1e-6:
                raise AssertionError('Exported context disagrees with saved forecast')
        recordings.append({'hour': hour, 'evaluation_samples': len(p), 'rows': rows})
    payload = {
        'schema': 'receipt_token_visual_lab_v1', 'results': result,
        'per_hour': json.loads((trial/'PER_HOUR.json').read_text()),
        'preprocessing': model.meta, 'labels': LABELS, 'recordings': recordings,
        'source_predictions_sha256': hashlib.sha256((trial/'PREDICTIONS.csv.gz').read_bytes()).hexdigest(),
        'note': 'Historical development evidence. Charts systematically subsample contexts; summary scores use every evaluation sample.',
    }
    template = (root/'src/simulation/token_lab_template.html').read_text()
    if template.count('__LAB_DATA__') != 1:
        raise ValueError('Exactly one data placeholder required')
    data = json.dumps(payload, separators=(',', ':'), allow_nan=False).replace('</', '<\\/')
    page = template.replace('__LAB_DATA__', data)
    path = trial/'bitcoin_token_lab.html'
    path.write_text(page)
    # The deployment carries only this generated, dependency-free view.
    public = root/'src/simulation/bitcoin_token_lab.html'
    public.write_text(page)
    print(json.dumps({'file': str(path), 'bytes': path.stat().st_size,
                      'charted_contexts': sum(len(r['rows']) for r in recordings),
                      'evaluation_samples': result['evaluation_samples']}))

if __name__ == '__main__':
    p = argparse.ArgumentParser()
    p.add_argument('--repo', default='.')
    p.add_argument('--upload', required=True)
    a = p.parse_args()
    export(a.repo, a.upload)
