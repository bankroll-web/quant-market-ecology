"""Audit source identity, trade integrity and timing for the ecology study."""
import argparse
import hashlib
import json
from pathlib import Path
import numpy as np
import pyarrow.parquet as pq
from .book_changes import plain
from .ecology_price_mechanics import HOURS


def audit(raw_dir,recovered_dir,states_dir,hours=HOURS):
    report={}
    for hour in hours:
        candidates=list(Path(recovered_dir).glob(f'BTCUSDT_orderbook_{hour}*.parquet')) or list(Path(raw_dir).glob(f'BTCUSDT_orderbook_{hour}*.parquet'))
        # Midnight must use the complete recovered original, never a truncated copy.
        bp=sorted(candidates)[0];tp=Path(raw_dir)/f'BTCUSDT_trades_{hour}.parquet'
        sources={}
        for path in (bp,tp):
            source,temporary=plain(path)
            try:
                f=pq.ParquetFile(source)
                sources[path.name]=dict(bytes=path.stat().st_size,sha256=hashlib.sha256(path.read_bytes()).hexdigest(),rows=f.metadata.num_rows)
                if path==tp:
                    data=f.read(columns=['received_time','trade_time','trade_id','quantity','price','is_buyer_maker','order_type']).to_pydict()
            finally:
                if temporary:Path(source).unlink()
        ids=np.array(data['trade_id'],dtype=np.int64);times=np.array(data['received_time'],dtype=np.int64)
        ages=(times-np.array(data['trade_time'],dtype=np.int64)*1000000)/1e6
        qty=np.array(data['quantity'],dtype=float);prices=np.array(data['price'],dtype=float)
        missing=(qty==0)&(prices==0)&(np.array(data['order_type'])=='NA')
        integrity=dict(duplicate_trade_ids=int(len(ids)-len(set(ids.tolist()))),backward_receipt_steps=int(np.sum(np.diff(times)<0)),
                       nonincreasing_trade_id_steps=int(np.sum(np.diff(ids)<=0)),positive_id_gap_steps=int(np.sum(np.diff(ids)>1)),
                       missing_trade_ids=int(np.maximum(np.diff(ids)-1,0).sum()),
                       missing_payload_records=int(np.sum(missing)),
                       nonpositive_or_nonfinite_qty=int(np.sum(((qty<=0)|~np.isfinite(qty))&~missing)),
                       nonpositive_or_nonfinite_price=int(np.sum(((prices<=0)|~np.isfinite(prices))&~missing)),
                       missing_maker_flags=sum(x is None for x in data['is_buyer_maker']),negative_age_trades=int(np.sum(ages<0)),
                       age_ms_quantiles={str(q):float(np.quantile(ages,q)) for q in (.05,.5,.95,.99)},
                       fresh_250ms_fraction=float(np.mean((ages>=0)&(ages<=250))))
        if any(integrity[k] for k in ('duplicate_trade_ids','backward_receipt_steps','nonincreasing_trade_id_steps','nonpositive_or_nonfinite_qty','nonpositive_or_nonfinite_price','missing_maker_flags')):
            raise ValueError(f'{hour}: invalid trade input: {integrity}')
        report[hour]=dict(sources=sources,trade_integrity=integrity,
                         reconstruction=json.loads((Path(states_dir)/f'BTCUSDT_orderbook_{hour}_observed_changes.json').read_text()))
    return report


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--raw-dir',required=True);p.add_argument('--recovered-dir',required=True);p.add_argument('--states-dir',required=True);p.add_argument('--out',required=True);a=p.parse_args()
    out=Path(a.out);out.parent.mkdir(parents=True,exist_ok=True)
    out.write_text(json.dumps(audit(a.raw_dir,a.recovered_dir,a.states_dir),indent=2)+'\n')
