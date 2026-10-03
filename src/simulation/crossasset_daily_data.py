"""Verified public daily bars, normalized UTC timestamps and explicit coverage audit."""
import calendar,csv,datetime as dt,hashlib,io,json,urllib.request,zipfile
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
SYMBOLS=('BTCUSDT','ETHUSDT','DOGEUSDT','BNBUSDT','XRPUSDT','ADAUSDT','LTCUSDT','TRXUSDT','LINKUSDT','ETCUSDT')

def normalize_ns(value):
    value=int(value)
    return value*(1000 if value>=10**14 else 10**6)

def months():
    return [f'{y}-{m:02d}' for y in range(2023,2027) for m in range(1,13) if (y,m)<=(2026,8)]

def fetch(symbol,month,cache):
    name=f'{symbol}-1d-{month}.zip';url=f'https://data.binance.vision/data/spot/monthly/klines/{symbol}/1d/{name}'
    path=Path(cache)/name;checkpath=Path(cache)/(name+'.CHECKSUM')
    if not path.exists():path.write_bytes(urllib.request.urlopen(url,timeout=30).read())
    if not checkpath.exists():checkpath.write_bytes(urllib.request.urlopen(url+'.CHECKSUM',timeout=30).read())
    payload=path.read_bytes();sha=hashlib.sha256(payload).hexdigest();expected=checkpath.read_text().split()[0]
    if sha!=expected:raise ValueError('Checksum mismatch: '+name)
    with zipfile.ZipFile(io.BytesIO(payload)) as z:
        if len(z.namelist())!=1:raise ValueError('Unexpected zip members')
        raw=list(csv.reader(io.StringIO(z.read(z.namelist()[0]).decode())))
    rows=[]
    for r in raw:
        if not r or r[0].lower().startswith('open'):continue
        t=normalize_ns(r[0]);close_ns=normalize_ns(r[6]);date=dt.datetime.fromtimestamp(t/1e9,dt.timezone.utc)
        o,h,l,c,v,q=map(float,[r[1],r[2],r[3],r[4],r[5],r[7]])
        if date.hour or date.minute or date.second or date.microsecond:raise ValueError('Non-midnight open')
        if not(0<l<=min(o,c)<=max(o,c)<=h and v>0 and q>0):raise ValueError('Invalid OHLC/volume')
        if not(t+86_400_000_000_000-1_000_000<=close_ns<t+86_400_000_000_000):raise ValueError('Invalid close timestamp')
        rows.append(dict(date=date.date().isoformat(),open_ns=t,close_ns=close_ns,open=o,high=h,low=l,close=c,base_volume=v,quote_volume=q,trades=int(r[8])))
    year,mon=map(int,month.split('-'))
    expected_dates=[dt.date(year,mon,d).isoformat() for d in range(1,calendar.monthrange(year,mon)[1]+1)]
    if [r['date'] for r in rows]!=expected_dates:raise ValueError('Missing/duplicate/unordered daily bars: '+name)
    return rows,dict(symbol=symbol,month=month,url=url,sha256=sha,checksum_verified=True,rows=len(rows))

def run(root):
    root=Path(root);cache=root/'data/raw/crossasset_daily';cache.mkdir(parents=True,exist_ok=True)
    out=root/'data/processed/crossasset_daily';out.mkdir(parents=True,exist_ok=True)
    doc=root/'docs/crossasset_daily';doc.mkdir(parents=True,exist_ok=True)
    jobs=[(s,m) for s in SYMBOLS for m in months()];results={};errors=[]
    def task(job):return job,fetch(*job,cache)
    with ThreadPoolExecutor(max_workers=8) as ex:
        futures=[ex.submit(task,j) for j in jobs]
        for f,j in zip(futures,jobs):
            try:key,value=f.result();results[key]=value
            except Exception as e:errors.append(dict(symbol=j[0],month=j[1],error=str(e)))
    if errors:
        (doc/'DOWNLOAD_ERRORS.json').write_text(json.dumps(errors,indent=2)+'\n');raise ValueError(f'{len(errors)} downloads failed; no complete dataset claimed')
    dates=None;audit=[]
    for symbol in SYMBOLS:
        rows=[r for month in months() for r in results[symbol,month][0]]
        if dates is None:dates=[r['date'] for r in rows]
        if [r['date'] for r in rows]!=dates:raise ValueError('Crossasset clock mismatch')
        with (out/(symbol+'.csv')).open('w') as f:
            writer=csv.DictWriter(f,fieldnames=list(rows[0]));writer.writeheader();writer.writerows(rows)
        manifest=[results[symbol,m][1] for m in months()]
        (doc/(symbol+'_SOURCES.json')).write_text(json.dumps(manifest,indent=2)+'\n')
        audit.append(dict(symbol=symbol,rows=len(rows),first=rows[0]['date'],last=rows[-1]['date'],csv_sha256=hashlib.sha256((out/(symbol+'.csv')).read_bytes()).hexdigest()))
    report=dict(status='verified_synchronized_daily_bars',archives=len(jobs),symbols=audit,missing_dates=0,duplicates=0,normalization='pre2025 milliseconds / post2025 microseconds to ns',source='https://github.com/binance/binance-public-data')
    (doc/'DATA_AUDIT.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report,indent=2))
    return report
if __name__=='__main__':
    import sys
    run(sys.argv[1])
