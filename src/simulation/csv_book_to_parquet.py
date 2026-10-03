"""Stream original depth CSV to replayable Parquet without float timestamp inference."""
import argparse
import hashlib
import json
from pathlib import Path
import pyarrow as pa
import pyarrow.compute as pc
import pyarrow.csv as pacsv
import pyarrow.parquet as pq
from .book_changes import COLS


def convert(source,target):
    source=Path(source);target=Path(target);target.parent.mkdir(parents=True,exist_ok=True)
    identifiers=['first_update_id','final_update_id','prev_final_update_id','last_update_id']
    types={k:pa.int64() for k in ['received_time','event_time','transaction_time']}
    types.update({k:pa.string() for k in identifiers+['event_type','side','price','quantity']})
    reader=pacsv.open_csv(source,read_options=pacsv.ReadOptions(block_size=4*1024*1024),
                         convert_options=pacsv.ConvertOptions(include_columns=COLS,column_types=types,strings_can_be_null=True))
    writer=None;rows=0
    try:
        for batch in reader:
            arrays=[]
            for name in COLS:
                column=batch.column(batch.schema.get_field_index(name))
                if name in identifiers:
                    # Decimal .0 notation in legacy exports must remain integral.
                    decimal=pc.cast(column,pa.decimal128(30,6));column=pc.cast(decimal,pa.int64(),safe=True)
                arrays.append(column)
            table=pa.Table.from_arrays(arrays,names=COLS)
            if writer is None:writer=pq.ParquetWriter(target,table.schema,compression='zstd')
            writer.write_table(table);rows+=len(table)
    finally:
        if writer:writer.close()
    if pq.ParquetFile(target).metadata.num_rows!=rows:raise ValueError('Incomplete conversion')
    result=dict(source=source.name,source_sha256=hashlib.sha256(source.read_bytes()).hexdigest(),source_bytes=source.stat().st_size,
                output=target.name,output_sha256=hashlib.sha256(target.read_bytes()).hexdigest(),rows=rows,
                method='Streaming Arrow CSV; int64 timestamps; exact decimal update IDs safely cast to int64. Selected replay columns only.')
    target.with_suffix('.conversion.json').write_text(json.dumps(result,indent=2)+'\n');return result


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('source');p.add_argument('target');a=p.parse_args();print(json.dumps(convert(a.source,a.target),indent=2))
