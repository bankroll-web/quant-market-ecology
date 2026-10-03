"""Fetch the exact official archive and verify its published checksum."""
import hashlib,urllib.request
from pathlib import Path

def download(out):
    out=Path(out);out.mkdir(parents=True,exist_ok=True)
    name='BTCUSDT-aggTrades-2026-09.zip'
    url='https://data.binance.vision/data/futures/um/monthly/aggTrades/BTCUSDT/'+name
    for suffix in ['', '.CHECKSUM']:
        urllib.request.urlretrieve(url+suffix,out/(name+suffix))
    expected=(out/(name+'.CHECKSUM')).read_text().split()[0]
    with (out/name).open('rb') as f:actual=hashlib.file_digest(f,'sha256').hexdigest()
    if expected!=actual:raise ValueError('Archive checksum mismatch')
    return out/name
if __name__=='__main__':
    import sys
    print(download(sys.argv[1]))
