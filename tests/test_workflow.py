import json
import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import patch
from iran_proxy_monitor.models import Probe, Speed
from iran_proxy_monitor.settings import Settings
from iran_proxy_monitor import monitor
from iran_proxy_monitor import exporter

class FakeEngine:
    def __init__(self,settings,stop):self.binary='fake-sing-box';self.version='sing-box simulated core'
    def connectivity(self,nodes,callback):
        return {n.id:Probe(n.id,True,round(80+i*4,2)) for i,n in enumerate(nodes)}
    def throughput(self,nodes,max_bytes,budget,callback,phase="preliminary",sizes=None):
        out={}
        for i,n in enumerate(nodes):out[n.id]=Speed(n.id,5.0-i*.2,max_bytes,5.3 if phase=='confirmation' else 1.3,True,endpoint='test',verified=(phase=='confirmation'))
        return out,max_bytes*len(nodes)
    def baseline(self):return 6.5

class FullCycleTests(unittest.TestCase):
    def test_full_pipeline_updates_exports_and_never_changes_source(self):
        with tempfile.TemporaryDirectory() as directory:
            d=Path(directory)
            source=d/'subscription.txt'
            text='\n'.join(f'trojan://secret@node{i}.example:443?sni=host.example#N{i}' for i in range(6))
            source.write_text(text,'utf-8')
            settings=Settings(subscription_url=source.as_uri(),budget_mib=4,prelim_kib=64,
                              confirm_min_kib=128,confirm_max_kib=256,shortlist_size=5,
                              probes_per_cycle=10,baseline_kib=0)
            settings.validate()
            outputs=d/'exports';outputs.mkdir()
            original=source.read_bytes()
            def history_factory():
                from iran_proxy_monitor.history import History
                return History(d/'observations.sqlite3')
            with patch.object(monitor,'SNAPSHOT',d/'snapshot.dat'),\
                 patch.object(monitor,'DATA_DIR',d),\
                 patch.object(exporter,'OUT',outputs),\
                 patch.object(monitor,'History',history_factory),\
                 patch.object(monitor,'SingboxEngine',FakeEngine),\
                 patch.object(exporter,'check_core',return_value=True):
                stats=monitor.run_cycle(settings,threading.Event())
            self.assertEqual(source.read_bytes(),original)
            self.assertEqual(stats['total'],6)
            self.assertEqual(stats['connected'],6)
            self.assertGreater(stats['fastest_mbps'],0)
            self.assertIn('best-download-speed',stats['exports'])
            self.assertIn('best-ping',stats['exports'])
            self.assertIn('best-overall',stats['exports'])
            exported=json.loads((outputs/'best-download-speed-latest.json').read_text('utf-8'))
            self.assertEqual(exported['outbounds'][-1]['type'],'selector')
            self.assertEqual(len(exported['outbounds']),6)
            self.assertTrue((d/'unsupported-nodes.csv').exists())

if __name__=='__main__':unittest.main()
