"""Causal receipt-clock adapter for the frozen D09/D09B development tapes.

Book features retain the reconstructed event sequence. Trade features are a
different, explicitly versioned language: trades received in [previous book
receipt, current book receipt). Current-receipt ties are deferred, never guessed.
There is no wait for an event-time interval to become retrospectively complete.
"""
from pathlib import Path
import hashlib
import numpy as np
import pyarrow.parquet as pq
from tokenizer_v1 import load_hours
from src.simulation.book_changes import plain

POLICY = {
    'version': 'receipt_window_v1',
    'trade_window': '[previous_book_receipt_ns, current_book_receipt_ns)',
    'decision': 'current_book_receipt_ns',
    'processing_latency_ms': 0,
    'tie_policy': 'exclude current-receipt trade ties; include them in next window',
    'book_order': 'original reconstructed episode sequence; reject receipt reversals/ties',
    'dt_token': 'elapsed book receipt milliseconds',
    'target': 'next 10 contiguous book updates, all strictly after decision receipt',
}

def receipt_trade_windows(receipt_ns, quantity, buyer_maker, starts, ends):
    """Arrival-window counts and quantities; future-arriving trades cannot enter."""
    receipts = np.asarray(receipt_ns, dtype=np.int64)
    q = np.asarray(quantity, dtype=float)
    maker = np.asarray(buyer_maker, dtype=bool)
    if not (len(receipts) == len(q) == len(maker)):
        raise ValueError('Trade arrays must align')
    if np.any(~np.isfinite(q)) or np.any(q < 0) or np.any(receipts <= 0):
        raise ValueError('Invalid raw trade quantity or receipt')
    starts, ends = np.asarray(starts, dtype=np.int64), np.asarray(ends, dtype=np.int64)
    if np.any(ends <= starts):
        raise ValueError('Receipt windows must be strictly increasing')
    order = np.argsort(receipts, kind='stable')
    times, qty = receipts[order], q[order]
    lo = np.searchsorted(times, starts, side='left')
    hi = np.searchsorted(times, ends, side='left')
    total = np.r_[0., np.cumsum(qty)]
    signed = np.r_[0., np.cumsum(qty * np.where(maker[order], -1., 1.))]
    return hi-lo, total[hi]-total[lo], signed[hi]-signed[lo]

def adapt_hour(df, receipt_ns, quantity, buyer_maker):
    df = df.copy()
    book = df['received_time_ns'].to_numpy(dtype=np.int64)
    event = df['t1_event_time_ms'].to_numpy(dtype=np.int64)
    ep = df['episode_id'].to_numpy()
    ix = df['interval_index'].to_numpy()
    valid = np.zeros(len(df), dtype=bool)
    valid[1:] = ((ep[1:] == ep[:-1]) & (ix[1:] == ix[:-1]+1)
                 & (event[1:] > event[:-1]) & (book[1:] > book[:-1]))
    # A future-dated book is rejected, not repaired by moving its timestamp.
    valid &= (book > 0) & (event * 10**6 <= book)
    valid[1:] &= event[:-1] * 10**6 <= book[:-1]
    rows = np.flatnonzero(valid)
    n, total, signed = receipt_trade_windows(receipt_ns, quantity, buyer_maker,
                                            book[rows-1], book[rows])
    df['receipt_valid'] = valid
    # Invalid rows receive placeholders but are never part of a sample.
    df['n_trades'], df['total_flow_qty'], df['signed_flow_qty'] = 0, 0., 0.
    df['interval_ms'] = 0.
    df.loc[rows, 'n_trades'] = n
    df.loc[rows, 'total_flow_qty'] = total
    df.loc[rows, 'signed_flow_qty'] = signed
    df.loc[rows, 'interval_ms'] = (book[rows]-book[rows-1])/1e6
    df['decision_receipt_ns'] = book
    return df

def load_receipt_hours(repo, upload):
    hours, reports = [], []
    for frozen in load_hours(repo):
        hour = frozen['hour'].iloc[0]
        path = Path(upload) / ('BTCUSDT_trades_' + hour + '.parquet')
        source, temporary = plain(path)
        try:
            raw = pq.read_table(source, columns=['received_time', 'quantity', 'is_buyer_maker']).to_pydict()
        finally:
            if temporary:
                Path(source).unlink()
        adapted = adapt_hour(frozen, raw['received_time'], raw['quantity'], raw['is_buyer_maker'])
        valid = adapted['receipt_valid'].to_numpy()
        reports.append({
            'hour': hour, 'rows': len(adapted), 'valid_receipt_rows': int(valid.sum()),
            'invalid_receipt_rows': int((~valid).sum()),
            'changed_trade_count_rows': int((valid & (adapted['n_trades'].values != frozen['n_trades'].values)).sum()),
            'changed_signed_flow_rows': int((valid & ~np.isclose(adapted['signed_flow_qty'], frozen['signed_flow_qty'], atol=1e-6, rtol=1e-6)).sum()),
            'raw_trade_sha256': hashlib.sha256(path.read_bytes()).hexdigest(),
        })
        hours.append(adapted)
    return hours, reports

def receipt_samples(df, tokens, context=16, horizon=10):
    """Causal inputs, decision-price anchor and strictly subsequent targets."""
    a = tokens.to_numpy()
    ep = df['episode_id'].to_numpy()
    event = df['t1_event_time_ms'].to_numpy()
    ix = df['interval_index'].to_numpy()
    receipt = df['decision_receipt_ns'].to_numpy(dtype=np.int64)
    valid = df['receipt_valid'].to_numpy(dtype=bool)
    mid = df['mid_t1'].to_numpy(dtype=float)
    signed, total = df['signed_flow_qty'].to_numpy(), df['total_flow_qty'].to_numpy()
    out = []
    for j in range(context-1, len(df)-horizon, horizon):
        lo, hi = j-context+1, j+horizon
        sl = slice(lo, hi+1)
        if (not valid[sl].all() or len(set(ep[sl])) != 1
                or np.any(np.diff(ix[sl]) != 1) or np.any(np.diff(event[sl]) <= 0)
                or np.any(np.diff(receipt[sl]) <= 0)
                or np.any(~np.isfinite(mid[sl])) or np.any(mid[sl] <= 0)):
            continue
        qty = total[j+1:hi+1].sum()
        out.append((a[lo:j+1], a[j+1], 10000*np.log(mid[hi]/mid[j]),
                    np.nan if qty <= 0 else signed[j+1:hi+1].sum()/qty,
                    10000*np.mean(np.abs(np.diff(np.log(mid[j:hi+1])))),
                    receipt[j], receipt[hi], mid[j], mid[hi],
                    df['hour'].iloc[j], ep[j]))
    if not out:
        raise ValueError('No contiguous receipt-valid examples')
    return [np.array(x) for x in zip(*out)]
