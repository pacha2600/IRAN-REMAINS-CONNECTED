"""SQLite observations, round-robin discovery and reliable-node scoring."""
from __future__ import annotations
import sqlite3
import json
import random
import time
from pathlib import Path
from .models import Node, Result, Probe
from .settings import DATA_DIR

class History:
    def __init__(self,path:Path | None=None):
        self.db=sqlite3.connect(path or DATA_DIR/'history.sqlite3')
        self.db.execute('PRAGMA journal_mode=WAL')
        self.db.executescript('''
        CREATE TABLE IF NOT EXISTS observations(
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          node_id TEXT NOT NULL,stamp REAL NOT NULL,available INTEGER NOT NULL,
          latency_ms REAL,mbps REAL,bytes INTEGER DEFAULT 0,error_class TEXT DEFAULT ''
        );
        CREATE INDEX IF NOT EXISTS ix_node_stamp ON observations(node_id,stamp DESC);
        CREATE TABLE IF NOT EXISTS registry(
          node_id TEXT PRIMARY KEY,name TEXT,protocol TEXT,server TEXT,port INTEGER,
          last_seen REAL, last_tested REAL DEFAULT 0
        );
        CREATE TABLE IF NOT EXISTS state(key TEXT PRIMARY KEY,value TEXT);
        ''')
        self.db.commit()

    def close(self):self.db.close()

    def register(self,nodes):
        now=time.time()
        with self.db:
            self.db.executemany('''INSERT INTO registry(node_id,name,protocol,server,port,last_seen)
            VALUES(?,?,?,?,?,?) ON CONFLICT(node_id) DO UPDATE SET name=excluded.name,
            protocol=excluded.protocol,server=excluded.server,port=excluded.port,last_seen=excluded.last_seen''',
            ((n.id,n.name,n.protocol,str(n.outbound.get('server','')),int(n.outbound.get('server_port',0)),now) for n in nodes))

    def recent(self,nodes, horizon=14):
        if not nodes:return {}
        cutoff=time.time()-horizon*86400
        result={}
        ids={n.id for n in nodes}
        # SQLite read all observations for a bounded 14-day window; index on stamp recommended.
        for id,ok,lat,mbps,stamp in self.db.execute('SELECT node_id,available,latency_ms,mbps,stamp FROM observations WHERE stamp>=? ORDER BY stamp DESC',(cutoff,)):
            if id not in ids:continue
            r=result.setdefault(id,{'success':0,'fail':0,'mbps':[], 'last':stamp,'latency':None})
            if ok:r['success']+=1
            else:r['fail']+=1
            if mbps is not None and mbps>0 and len(r['mbps'])<12:r['mbps'].append(mbps)
            if r['latency'] is None and lat is not None:r['latency']=lat
        return result

    def reliability(self, h):
        if not h:return 0.50
        return (h['success']+1)/(h['success']+h['fail']+2)

    def select_probes(self,nodes,limit,all_nodes=False):
        supported=[n for n in nodes if n.supported]
        if all_nodes or len(supported)<=limit:return supported
        history=self.recent(supported)
        rng=random.Random(int(time.time()//3600))
        last_known=[];previously=[];unseen=[]
        for n in supported:
            r=history.get(n.id)
            if not r:unseen.append(n)
            elif r['success']:last_known.append(n)
            else:previously.append(n)
        last_known.sort(key=lambda n:(-max(history[n.id]['mbps'] or [0]),-history[n.id]['last']))
        # Diverse allocation: 45% known-good, 35% rotating unseen, 20% previously failed.
        # If a category is empty, remaining slots are filled by the others.
        chosen=[];seen=set()
        def take(arr,count,randomize=False):
            if randomize:rng.shuffle(arr)
            for n in arr:
                if len(chosen)>=limit or count<=0:break
                if n.id not in seen:chosen.append(n);seen.add(n.id);count-=1
        take(last_known,round(limit*.45))
        # Persist cursor so previously untested nodes are covered even across app restarts.
        cursor=int(self.get_state('unseen_cursor','0'))
        unseen.sort(key=lambda n:n.id)
        rotated=unseen[cursor%len(unseen):]+unseen[:cursor%len(unseen)] if unseen else []
        quota=round(limit*.35)
        take(rotated,quota)
        self.set_state('unseen_cursor',cursor+quota)
        take(previously,round(limit*.2),randomize=True)
        rest=[n for n in supported if n.id not in seen]
        rng.shuffle(rest)
        take(rest,limit)
        return chosen

    def select_speeds(self, connected, limit):
        if len(connected)<=limit:return connected
        h=self.recent([r[0] for r in connected]); rng=random.Random(int(time.time()//3600))
        ranking=sorted(connected,key=lambda item:(
            -max(h.get(item[0].id,{}).get('mbps',[]) or [0]),
            item[1].latency_ms or 1e6))
        head=ranking[:int(limit*.70)]
        rest=ranking[int(limit*.70):]
        rng.shuffle(rest)
        return head+rest[:limit-len(head)]

    def record(self, node:Node, probe:Probe, mbps=None, nbytes=0):
        # Only broad error classes, never exception messages that can contain a URL/credential.
        classification='ok' if probe.ok else ('core' if 'core' in probe.error else 'network')
        now=time.time()
        with self.db:
            self.db.execute('''INSERT INTO observations(node_id,stamp,available,latency_ms,mbps,bytes,error_class)
                           VALUES(?,?,?,?,?,?,?)''',
                           (node.id,now,int(probe.ok),probe.latency_ms,mbps,nbytes,classification))
            self.db.execute('UPDATE registry SET last_tested=? WHERE node_id=?',(now,node.id))

    def get_state(self,key,default=''):
        row=self.db.execute('SELECT value FROM state WHERE key=?',(key,)).fetchone()
        return row[0] if row else default

    def set_state(self,key,value):
        with self.db:
            self.db.execute('INSERT INTO state(key,value) VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value',
                            (key,str(value)))

    def trim(self):
        with self.db:
            self.db.execute('DELETE FROM observations WHERE stamp < ?',(time.time()-60*86400,))
