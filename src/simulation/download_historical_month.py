"""Fetch the exact official archive and verify its published checksum."""
import hashlib,urllib.request,re
from pathlib import Path

def download(out,month="2026-09"):
    if not re.fullmatch(r"\d{4}-(0[1-9]|1[0-2])",month):raise ValueError("Invalid month")
    out=Path(out);out.mkdir(parents=True,exist_ok=True)
    name='BTCUSDT-aggTrades-'+month+'.zip'
    url='https://data.binance.vision/data/futures/um/monthly/aggTrades/BTCUSDT/'+name
    for suffix in ['', '.CHECKSUM']:
        urllib.request.urlretrieve(url+suffix,out/(name+suffix))
    expected=(out/(name+'.CHECKSUM')).read_text().split()[0]
    with (out/name).open('rb') as f:actual=hashlib.file_digest(f,'sha256').hexdigest()
    if expected!=actual:raise ValueError('Archive checksum mismatch')
    return out/name
if __name__=='__main__':
    import sys
    print(download(sys.argv[1],sys.argv[2] if len(sys.argv)>2 else "2026-09"))
