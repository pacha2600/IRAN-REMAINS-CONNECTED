import tempfile
import unittest
from pathlib import Path
from iran_proxy_monitor.history import History
from iran_proxy_monitor.parser import link_node
from iran_proxy_monitor.models import Probe

class HistoryTests(unittest.TestCase):
    def test_rotation_and_reliability(self):
        with tempfile.TemporaryDirectory() as temp:
            history=History(Path(temp)/'db.sqlite')
            nodes=[link_node(f'trojan://p@node{i}.example:443#node{i}') for i in range(90)]
            history.register(nodes)
            subset=history.select_probes(nodes,20)
            self.assertEqual(len(subset),20)
            self.assertEqual(len(set(n.id for n in subset)),20)
            self.assertEqual(len(history.select_probes(nodes,20,True)),90)
            history.record(nodes[0],Probe(nodes[0].id,True,120),8.5,1024)
            r=history.recent(nodes)
            self.assertEqual(r[nodes[0].id]['success'],1)
            self.assertGreater(history.reliability(r[nodes[0].id]),.5)
            history.close()

if __name__=='__main__':unittest.main()
