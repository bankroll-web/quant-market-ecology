"""Fixed-budget, receipt-aware Bitcoin token experiment; never enables orders."""
import argparse
import hashlib
import json
from pathlib import Path
import numpy as np
import pandas as pd
import torch
from torch import nn
from tokenizer_v1 import MarketTokenizer, TICK, QLEVELS, MID_EDGES, NTR_EDGES
from train_real import Model, FIELDS, L, H, QS
from receipt_tokens import POLICY, load_receipt_hours, receipt_samples

def forecast(model, x, return_scale, vol_scale):
    model.eval()
    prob = [[] for _ in FIELDS]
    qp, fp, vp = [], [], []
    with torch.no_grad():
        for j in range(0, len(x), 256):
            fields, q, f, v = model(torch.tensor(x[j:j+256]))
            qp.extend((q*return_scale).numpy())
            fp.extend(f.numpy())
            vp.extend((v*vol_scale).numpy())
            for i, field in enumerate(fields):
                prob[i].extend(field.softmax(1).numpy())
    return [np.asarray(p) for p in prob], np.asarray(qp), np.asarray(fp), np.asarray(vp)

def run(repo, upload):
    root = Path(repo)
    out = root / 'docs/market_tokens/receipt_trial'
    out.mkdir(parents=True, exist_ok=True)
    torch.set_num_threads(2)
    torch.manual_seed(91)
    rng = np.random.default_rng(91)
    hours, receipt_report = load_receipt_hours(root, upload)
    if len(hours) != 5:
        raise ValueError('Expected fixed five-hour development corpus')
    train, test = pd.concat(hours[:3], ignore_index=True), pd.concat(hours[3:], ignore_index=True)
    for df in (train, test):
        df['episode_id'] = df['hour'] + '_' + df['episode_id'].astype(str)
    tk = MarketTokenizer().fit(train.loc[train['receipt_valid']])
    tr, _ = tk.transform(train)
    te, _ = tk.transform(test)
    a, b = receipt_samples(train, tr), receipt_samples(test, te)
    x, y, ret, flow, vol = a[:5]
    xx, yy, rr, ff, vv = b[:5]
    if a[6].max() >= b[5].min():
        raise AssertionError('Training targets overlap the evaluation period')
    rs, vs = max(ret.std(), 1e-6), max(vol.std(), 1e-6)
    model = Model(tk.vocab)
    opt = torch.optim.AdamW(model.parameters(), lr=.001)
    qs = torch.tensor(QS, dtype=torch.float32)
    losses = []
    for epoch in range(5):
        model.train()
        track = []
        for ids in np.array_split(rng.permutation(len(x)), int(np.ceil(len(x)/128))):
            fields, q, f, v = model(torch.tensor(x[ids]))
            err = torch.tensor(ret[ids]/rs, dtype=torch.float32)[:, None] - q
            fm = np.isfinite(flow[ids])
            loss = (sum(nn.functional.cross_entropy(z, torch.tensor(y[ids, i])) for i, z in enumerate(fields))/len(FIELDS)
                    + torch.maximum(qs*err, (qs-1)*err).mean()
                    + .3*((v-torch.tensor(vol[ids]/vs, dtype=torch.float32))**2).mean())
            if fm.any():
                loss = loss + .3*((f[fm]-torch.tensor(flow[ids][fm], dtype=torch.float32))**2).mean()
            opt.zero_grad()
            loss.backward()
            nn.utils.clip_grad_norm_(model.parameters(), 1)
            opt.step()
            track.append(float(loss.detach()))
        losses.append(float(np.mean(track)))
        print('epoch', epoch+1, losses[-1], flush=True)
    prob, q, f, v = forecast(model, xx, rs, vs)
    scores = {}
    baselines = {}
    for i, field in enumerate(FIELDS):
        size = tk.vocab[field]
        joint = np.ones((size, size))
        np.add.at(joint, (x[:, -1, i], y[:, i]), 1)
        cond = joint/joint.sum(1, keepdims=True)
        prior = np.bincount(y[:, i], minlength=size)+1
        prior = prior/prior.sum()
        truth = yy[:, i]
        scores[field] = {
            'transformer_bits': float(-np.log2(np.maximum(prob[i][np.arange(len(truth)), truth], 1e-12)).mean()),
            'bigram_bits': float(-np.log2(cond[xx[:, -1, i], truth]).mean()),
            'prior_bits': float(-np.log2(prior[truth]).mean()),
        }
        baselines['bigram_'+field], baselines['prior_'+field] = cond, prior
    baseq, baseflow, basevol = np.quantile(ret, QS), float(np.nanmean(flow)), float(vol.mean())
    err, baseerr = rr[:, None]-q, rr[:, None]-baseq
    fm = np.isfinite(ff)
    limits = [
        'All five hours were previously examined: development evidence, not an untouched evaluation period.',
        'Zero processing latency is an idealized diagnostic. No fees, queue, execution or net PnL tested.',
        'Frozen book reconstruction/provenance is inherited, not rebuilt from raw book messages here.',
        'Trade features now represent arrival windows, not complete exchange-event-time intervals; old metrics are not directly comparable.',
        'Raw trade files must contain every message received in these windows. Hour-file spillover and duplicate payloads are not independently verified.',
        'Tick 0.1 remains inherited; half-tick rounding and sweep/reset attribution remain unresolved.',
        'Context windows overlap and the ten-update horizon has variable elapsed time. Two evaluation hours cannot establish robustness.',
    ]
    result = {
        'status': 'receipt_window_v1_development', 'qualified': False, 'orders_enabled': False,
        'policy': POLICY, 'receipt_audit': receipt_report,
        'train_events': len(train), 'test_events': len(test),
        'training_samples': len(x), 'evaluation_samples': len(xx),
        'context_events': L, 'target_events': H, 'epochs': 5, 'seed': 91,
        'model_parameters': sum(p.numel() for p in model.parameters()),
        'training_losses': losses, 'field_scores': scores,
        'return_pinball_bps': float(np.maximum(QS*err, (QS-1)*err).mean()),
        'baseline_return_pinball_bps': float(np.maximum(QS*baseerr, (QS-1)*baseerr).mean()),
        'coverage_80': float(((rr >= q[:, 0]) & (rr <= q[:, -1])).mean()),
        'flow_mse': float(((f[fm]-ff[fm])**2).mean()),
        'baseline_flow_mse': float(((baseflow-ff[fm])**2).mean()),
        'flow_evaluation_samples': int(fm.sum()),
        'vol_mse': float(((v-vv)**2).mean()),
        'baseline_vol_mse': float(((basevol-vv)**2).mean()),
        'minimum_target_delay_ms': float(((b[6]-b[5])/1e6).min()),
        'median_target_delay_ms': float(np.median((b[6]-b[5])/1e6)),
        'future_targets_strictly_after_decision': bool(np.all(b[6] > b[5])),
        'last_training_target_receipt_ns': int(a[6].max()),
        'first_evaluation_decision_receipt_ns': int(b[5].min()),
        'source_sha256': {p.name: hashlib.sha256(p.read_bytes()).hexdigest()
                          for p in sorted((root/'data/frozen').glob('2026-*d09*.csv'))},
        'code_sha256': {name: hashlib.sha256((root/name).read_bytes()).hexdigest()
                        for name in ('receipt_tokens.py', 'train_receipt.py', 'train_real.py', 'tokenizer_v1.py')},
        'limits': limits,
    }
    (out/'RESULTS.json').write_text(json.dumps(result, indent=2)+'\n')
    preprocessing = {
        'policy': POLICY, 'fields': FIELDS, 'vocab': tk.vocab, 'tick_assumption': TICK,
        'mid_edges': MID_EDGES.tolist(), 'trade_count_edges': NTR_EDGES.tolist(),
        'quantile_fit_levels': QLEVELS, 'fit_hours': [h['hour'].iloc[0] for h in hours[:3]],
        'fit_only_receipt_valid_training_rows': True,
        'binners': {name: {key: value.tolist() if isinstance(value, np.ndarray) else value
                           for key, value in vars(binner).items()} for name, binner in tk.b.items()},
        'return_scale': float(rs), 'vol_scale': float(vs), 'quantile_levels': QS.tolist(),
        'baseline_return_quantiles': baseq.tolist(), 'baseline_flow_mean': baseflow,
        'baseline_vol_mean': basevol,
    }
    (out/'PREPROCESSING.json').write_text(json.dumps(preprocessing, indent=2)+'\n')
    np.savez_compressed(out/'WEIGHTS.npz', **{k: p.detach().numpy() for k, p in model.state_dict().items()})
    np.savez_compressed(out/'BASELINES.npz', **baselines)
    predictions = pd.DataFrame({
        'hour': b[9], 'episode_id': b[10], 'decision_receipt_ns': b[5], 'target_receipt_ns': b[6],
        'anchor_mid': b[7], 'target_mid': b[8], 'return_bps': rr,
        'future_flow': ff, 'future_vol': vv, 'predicted_flow': f, 'predicted_vol': v,
    })
    for i, level in enumerate(QS):
        predictions['return_q'+str(level)] = q[:, i]
    predictions.to_csv(out/'PREDICTIONS.csv.gz', index=False, compression={'method': 'gzip', 'mtime': 0})
    per_hour = {}
    for hour in np.unique(b[9]):
        mask = b[9] == hour
        flow_mask = mask & fm
        per_hour[str(hour)] = {
            'samples': int(mask.sum()),
            'return_pinball_bps': float(np.maximum(QS*err[mask], (QS-1)*err[mask]).mean()),
            'baseline_return_pinball_bps': float(np.maximum(QS*baseerr[mask], (QS-1)*baseerr[mask]).mean()),
            'flow_mse': float(((f[flow_mask]-ff[flow_mask])**2).mean()),
            'baseline_flow_mse': float(((baseflow-ff[flow_mask])**2).mean()),
            'vol_mse': float(((v[mask]-vv[mask])**2).mean()),
            'baseline_vol_mse': float(((basevol-vv[mask])**2).mean()),
        }
    (out/'PER_HOUR.json').write_text(json.dumps(per_hour, indent=2)+'\n')
    # Reload the persisted numerical weights: test the delivered model, not only memory.
    restored = Model(tk.vocab)
    with np.load(out/'WEIGHTS.npz', allow_pickle=False) as saved:
        restored.load_state_dict({k: torch.tensor(saved[k]) for k in saved.files})
    _, rq, rf, rv = forecast(restored, xx, rs, vs)
    reload_error = max(float(np.abs(q-rq).max()), float(np.abs(f-rf).max()), float(np.abs(v-rv).max()))
    if reload_error > 1e-7 or not result['future_targets_strictly_after_decision']:
        raise AssertionError('Saved-model reproduction or future-only targets failed')
    audit = {'saved_model_max_absolute_forecast_difference': reload_error,
             'all_targets_after_decision': result['future_targets_strictly_after_decision'],
             'artifacts_sha256': {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(out.iterdir()) if p.name != 'RUN_AUDIT.json' and p.suffix != '.md'}}
    (out/'RUN_AUDIT.json').write_text(json.dumps(audit, indent=2)+'\n')
    print(json.dumps({k: val for k, val in result.items() if k not in ('source_sha256', 'code_sha256', 'limits', 'field_scores')}, indent=2))
    return result

if __name__ == '__main__':
    p = argparse.ArgumentParser()
    p.add_argument('--repo', default='.')
    p.add_argument('--upload', required=True)
    args = p.parse_args()
    run(args.repo, args.upload)
