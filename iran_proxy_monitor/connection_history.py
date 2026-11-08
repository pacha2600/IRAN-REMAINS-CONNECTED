
"""Private, opt-in-by-use list of the last ten successfully connected profiles."""
import copy
import json
import os
import time
import hashlib
from pathlib import Path
from .settings import DATA_DIR

HISTORY_PATH=DATA_DIR/'client-recent.json'

def recent_connections(path: Path=HISTORY_PATH) -> list[dict]:
    try:
        data=json.loads(path.read_text('utf-8'))
        if not isinstance(data,list):return []
        return [x for x in data[:10] if isinstance(x,dict) and isinstance(x.get('outbound'),dict)
                and isinstance(x.get('id'),str) and isinstance(x.get('name'),str)]
    except (OSError,ValueError,TypeError):return []

def remember_connection(name: str, outbound: dict, mode: str, path: Path=HISTORY_PATH,
                        metrics: dict | None=None) -> list[dict]:
    if not isinstance(outbound,dict) or not outbound.get('type'):
        raise ValueError('A valid proxy outbound is required')
    key=hashlib.sha256(json.dumps(outbound,sort_keys=True,separators=(',',':')).encode('utf-8')).hexdigest()
    entry={'id':key,'name':str(name)[:125],'mode':mode,'connected_at':time.time(),
           'outbound':copy.deepcopy(outbound)}
    # Keep only table fields; never ingest credentials or freeform URLs into metrics.
    if metrics:
        allowed=('rank','latency','mbps','flow_mbps','seconds','reliability','confirmed','status')
        entry['metrics']={key:metrics[key] for key in allowed if key in metrics and
                          (isinstance(metrics[key],(int,float,bool)) or
                           key=='status' and isinstance(metrics[key],str))}
    entries=[entry]+[x for x in recent_connections(path) if x['id']!=key]
    path.parent.mkdir(parents=True,exist_ok=True)
    temp=path.with_suffix('.tmp')
    try:
        with temp.open('w',encoding='utf-8') as f:
            json.dump(entries[:10],f,ensure_ascii=False,indent=2)
        try:os.chmod(temp,0o600)
        except OSError:pass
        os.replace(temp,path)
    finally:
        temp.unlink(missing_ok=True)
    return entries[:10]

def clear_connections(path: Path=HISTORY_PATH):
    path.unlink(missing_ok=True)
