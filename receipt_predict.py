"""Load frozen Bitcoin tokenizer/model and forecast an already observed context.

This is a reusable inference adapter, not a live feed connection or trade bot.
"""
import argparse
import json
from pathlib import Path
import numpy as np
import pandas as pd
import torch
from tokenizer_v1 import MarketTokenizer, MagBinner, EdgeBinner, SPEC, TICK, MID_EDGES, NTR_EDGES, features
from train_real import Model, FIELDS, L, QS
from receipt_tokens import POLICY, load_receipt_hours

class ReceiptPredictor:
    def __init__(self, checkpoint):
        checkpoint = Path(checkpoint)
        self.meta = json.loads((checkpoint/'PREPROCESSING.json').read_text())
        if (self.meta['policy'] != POLICY or self.meta['fields'] != FIELDS
                or self.meta['tick_assumption'] != TICK
                or self.meta['mid_edges'] != MID_EDGES.tolist()
                or self.meta['trade_count_edges'] != NTR_EDGES.tolist()):
            raise ValueError('Incompatible tokenizer or receipt policy')
        self.tokenizer = MarketTokenizer()
        self.tokenizer.vocab = self.meta['vocab']
        self.tokenizer.b = {}
        for field, state in self.meta['binners'].items():
            kind, signed = SPEC[field]
            binner = MagBinner(signed) if kind == 'mag' else EdgeBinner(state['n'])
            for key, val in state.items():
                setattr(binner, key, np.asarray(val) if key in ('edges', 'centers') else val)
            self.tokenizer.b[field] = binner
        torch.set_num_threads(2)
        self.model = Model(self.meta['vocab'])
        with np.load(checkpoint/'WEIGHTS.npz', allow_pickle=False) as saved:
            self.model.load_state_dict({k: torch.tensor(saved[k]) for k in saved.files})
        self.model.eval()

    def predict(self, context):
        if len(context) != L:
            raise ValueError('Exactly 16 observed rows required')
        receipt = context['decision_receipt_ns'].to_numpy(dtype=np.int64)
        event = context['t1_event_time_ms'].to_numpy(dtype=np.int64)
        if (not context['receipt_valid'].all() or context['episode_id'].nunique() != 1
                or context['hour'].nunique() != 1
                or np.any(np.diff(context['interval_index']) != 1)
                or np.any(np.diff(event) <= 0) or np.any(np.diff(receipt) <= 0)
                or np.any(event*10**6 > receipt)):
            raise ValueError('Invalid or discontinuous receipt context')
        if not np.isfinite(features(context).to_numpy()).all() or not np.all(context['mid_t1'] > 0):
            raise ValueError('Invalid numerical context features')
        x, _ = self.tokenizer.transform(context)
        with torch.no_grad():
            _, q, f, v = self.model(torch.tensor(x.to_numpy()[None]))
        return {
            'policy_version': POLICY['version'], 'decision_receipt_ns': int(receipt[-1]),
            'anchor_mid': float(context['mid_t1'].iloc[-1]),
            'horizon': 'next 10 contiguous book updates',
            'return_quantiles_bps': {str(level): float(value)
                                     for level, value in zip(QS, (q[0]*self.meta['return_scale']).numpy())},
            'flow_forecast': float(f[0]), 'vol_forecast_bps': float(v[0]*self.meta['vol_scale']),
            'action': 'WAIT', 'qualified': False, 'orders_enabled': False,
            'reason': 'Development forecast; no validated executable policy',
        }

def example(repo, upload):
    root = Path(repo)
    out = root/'docs/market_tokens/receipt_trial'
    predictor = ReceiptPredictor(out)
    hours, _ = load_receipt_hours(root, upload)
    df = hours[-1]
    for end in range(len(df), L-1, -1):
        context = df.iloc[end-L:end]
        try:
            result = predictor.predict(context)
        except ValueError:
            continue
        (out/'EXAMPLE_FORECAST.json').write_text(json.dumps(result, indent=2)+'\n')
        print(json.dumps(result, indent=2))
        return result
    raise ValueError('No valid example context')

if __name__ == '__main__':
    p = argparse.ArgumentParser()
    p.add_argument('--repo', default='.')
    p.add_argument('--upload', required=True)
    args = p.parse_args()
    example(args.repo, args.upload)
