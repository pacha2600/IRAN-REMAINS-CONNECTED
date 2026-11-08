
"""Conservative daily accounting for completed scans.

Only counts observed HTTP response payload: it is NOT total ISP traffic.
No URL, proxy credentials, node names, or raw network content are stored.
"""
from __future__ import annotations
from datetime import datetime, timedelta
import json
import os
import time
from pathlib import Path
from .settings import DATA_DIR

SCAN_USAGE_PATH = DATA_DIR/'scan-usage.json'

def read_scan_usage(path: Path=SCAN_USAGE_PATH) -> dict:
    try:
        data=json.loads(path.read_text(encoding='utf-8'))
        if isinstance(data,dict) and isinstance(data.get('records'),list):return data
    except (OSError,ValueError,TypeError):pass
    return {'records':[]}

def daily_payload_bytes(day: str|None=None, path: Path=SCAN_USAGE_PATH) -> int:
    day=day or datetime.now().date().isoformat()
    return sum(int(row['bytes']) for row in read_scan_usage(path)['records']
        if row.get('day')==day and isinstance(row.get('bytes'),int) and row['bytes']>=0)

def record_scan_usage(payload_bytes:int, began:float, source_id:str, path:Path=SCAN_USAGE_PATH) -> float:
    if not isinstance(payload_bytes,int) or payload_bytes<0:raise ValueError('Invalid payload byte count')
    data=read_scan_usage(path)
    today=datetime.fromtimestamp(began).date().isoformat()
    cutoff=(datetime.now().date()-timedelta(days=90)).isoformat()
    rows=[x for x in data['records'] if isinstance(x,dict) and x.get('day','')>=cutoff]
    rows.append({'day':today,'timestamp':began,'bytes':payload_bytes,'source_id':source_id[:10]})
    path.parent.mkdir(parents=True,exist_ok=True)
    temp=path.with_suffix('.tmp')
    try:
        temp.write_text(json.dumps({'records':rows[-300:]},separators=(',',':')),encoding='utf-8')
        try:os.chmod(temp,0o600)
        except OSError:pass
        os.replace(temp,path)
    finally:temp.unlink(missing_ok=True)
    return round(sum(x['bytes'] for x in rows if x['day']==datetime.now().date().isoformat())/1048576,3)
