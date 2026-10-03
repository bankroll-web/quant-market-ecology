"""Audit-compatible L2 event replay and observed near-touch level-change tape."""
import argparse,csv,json,os,tempfile
from collections import Counter,defaultdict
from pathlib import Path
import pyarrow.parquet as pq
import zstandard as zstd

COLS=['received_time','event_time','transaction_time','event_type','first_update_id','final_update_id','prev_final_update_id','last_update_id','side','price','quantity']

def plain(path):
    with open(path,'rb') as f:magic=f.read(4)
    if magic==b'PAR1':return str(path),None
    if magic!=b'\x28\xb5\x2f\xfd':raise ValueError('Unknown format')
    temp=tempfile.NamedTemporaryFile(suffix='.parquet',delete=False)
    with open(path,'rb') as src,temp:zstd.ZstdDecompressor().copy_stream(src,temp)
    return temp.name,temp.name

def grouped(path):
    p,tmp=plain(path)
    try:
        groups={}
        for batch in pq.ParquetFile(p).iter_batches(batch_size=100000,columns=COLS):
            d=batch.to_pydict()
            for v in zip(*(d[k] for k in COLS)):
                received,event,trans,kind,U,u,pu,last,side,price,qty=v
                key=((kind,received,event,last) if kind=='snapshot'
                     else (kind,received,event,trans,U,u,pu))
                groups.setdefault(key,[]).append((side,float(price),float(qty)))
        ordered=sorted(groups.items(),key=lambda item:(item[0][1],0 if item[0][0]=='snapshot' else 1,
                                                     item[0][3] if item[0][0]=='snapshot' else item[0][5]))
        return ordered
    finally:
        if tmp:os.unlink(tmp)

def state(bids,asks):
    bid,ask=max(bids),min(asks)
    mid=(bid+ask)/2
    qb=bids[bid];qa=asks[ask]
    db=sum(q for p,q in bids.items() if p>=mid*.999)
    da=sum(q for p,q in asks.items() if p<=mid*1.001)
    return mid,(qb-qa)/(qb+qa),db,da,bid,ask

def best_quote_ofi(previous_bid,previous_bid_qty,previous_ask,previous_ask_qty,bid,bid_qty,ask,ask_qty):
    return ((bid_qty if bid>=previous_bid else 0.)-(previous_bid_qty if bid<=previous_bid else 0.)
            -(ask_qty if ask<=previous_ask else 0.)+(previous_ask_qty if ask>=previous_ask else 0.))

def replay(path,out):
    events=grouped(path);counts=Counter();bids={};asks={}
    valid=False;waiting=False;sequence=None;snapshot_id=None;previous_received=None;episode=0
    with open(out,'w',newline='') as f:
        writer=None
        for key,levels in events:
            kind,received,event=key[:3]
            if kind=='snapshot':
                bids={};asks={}
                for side,price,qty in levels:
                    if qty>0:(bids if side=='bid' else asks)[price]=qty
                sequence=snapshot_id=key[3];waiting=True;valid=False;previous_received=None
                counts['snapshots_loaded']+=1
                continue
            U,u,pu=key[4],key[5],key[6]
            if waiting:
                if u<=snapshot_id:
                    counts['stale_updates_skipped']+=1;continue
                if not U<=snapshot_id+1<=u:
                    counts['invalid_snapshot_bridges']+=1;valid=False;waiting=False;bids={};asks={};continue
                counts['valid_snapshot_bridges']+=1;episode+=1;waiting=False;valid=True
                bridge=True
            elif not valid:continue
            elif pu!=sequence:
                counts['sequence_failures']+=1;valid=False;bids={};asks={};previous_received=None;continue
            else:
                counts['continuous_updates']+=1;bridge=False
            if not bids or not asks:raise ValueError('Empty pre-event book')
            mid,obi,db,da,bid,ask=state(bids,asks)
            pre_bid_qty,pre_ask_qty=bids[bid],asks[ask]
            changes=Counter()
            for side,price,qty in levels:
                book=bids if side=='bid' else asks
                old=book.get(price,0.)
                if (side=='bid' and price>=mid*.999) or (side=='ask' and price<=mid*1.001):
                    if qty>old:
                        changes[side+'_add_levels']+=1;changes[side+'_add_qty']+=qty-old
                    elif qty<old:
                        changes[side+'_remove_levels']+=1;changes[side+'_remove_qty']+=old-qty
                if qty<=0:book.pop(price,None)
                else:book[price]=qty
            sequence=u;counts['valid_states']+=1
            if min(asks)<=max(bids):counts['crossed_locked_states']+=1
            dt=(received-previous_received)/1e9 if previous_received is not None else 0.
            if dt<0:raise ValueError('Nonmonotonic receipt time')
            previous_received=received
            if not bridge and dt>0:
                post_mid,post_obi,post_db,post_da,post_bid,post_ask=state(bids,asks)
                row={'received_time_ns':received,'event_time_ms':event,'episode':episode,
                     'exposure_seconds':dt,'pre_mid':mid,'pre_obi_top':obi,
                     'pre_bid_top_qty':pre_bid_qty, 'pre_ask_top_qty':pre_ask_qty,
                     'pre_bid_depth_10bps':db,'pre_ask_depth_10bps':da,
                     'pre_best_bid':bid,'pre_best_ask':ask,
                     'post_bid_top_qty':bids[post_bid],'post_ask_top_qty':asks[post_ask],
                     'best_quote_ofi_btc':best_quote_ofi(bid,pre_bid_qty,ask,pre_ask_qty,post_bid,bids[post_bid],post_ask,asks[post_ask]),
                     'post_mid':post_mid,'post_best_bid':post_bid,'post_best_ask':post_ask,
                     'post_spread':post_ask-post_bid,'post_obi_top':post_obi,
                     'post_bid_depth_10bps':post_db,'post_ask_depth_10bps':post_da,
                     **{name:changes[name] for side in ('bid','ask') for name in
                        (side+'_add_levels',side+'_remove_levels',side+'_add_qty',side+'_remove_qty')}}
                if writer is None:writer=csv.DictWriter(f,fieldnames=list(row));writer.writeheader()
                writer.writerow(row);counts['calibration_intervals']+=1
                counts['exposure_seconds']+=dt
    counts['valid_episodes']=episode
    return dict(counts)

if __name__=='__main__':
    ap=argparse.ArgumentParser();ap.add_argument('files',nargs='+',type=Path);ap.add_argument('--out',type=Path,required=True);a=ap.parse_args();a.out.mkdir(exist_ok=True,parents=True)
    for path in a.files:
        out=a.out/(path.stem.replace('(1)','').replace('(2)','')+'_observed_changes.csv')
        result=replay(path,out);print(path.name,json.dumps(result,indent=2))
        out.with_suffix('.json').write_text(json.dumps(result,indent=2)+'\n')
