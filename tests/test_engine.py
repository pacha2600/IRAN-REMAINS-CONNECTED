import unittest
from unittest.mock import patch
from iran_proxy_monitor.parser import link_node
from iran_proxy_monitor.engine import batch_config, available_ports, endpoint_order
from iran_proxy_monitor.exporter import shortlist_config

class EngineTests(unittest.TestCase):
    def setUp(self):
        self.a=link_node('vless://123e4567-e89b-12d3-a456-426614174000@node1.example:443?security=reality&sni=google.com&pbk=key&sid=aa#One')
        self.b=link_node('trojan://secret@node2.example:443?sni=example.com#Two')

    def test_unique_inbounds_and_no_direct_fallback(self):
        cfg=batch_config([self.a,self.b],[19001,19002])
        self.assertEqual(cfg['inbounds'][0]['listen'],'127.0.0.1')
        self.assertEqual(cfg['route']['final'],'block')
        self.assertEqual(cfg['route']['rules'][1]['outbound'],'node1')
        self.assertEqual(cfg['outbounds'][0]['tls']['reality']['public_key'],'key')
        self.assertEqual(len(cfg['outbounds']),3)
        self.assertEqual(cfg['route']['default_domain_resolver'],'local')

    def test_export_is_valid_shape_and_no_tun(self):
        cfg=shortlist_config([self.a,self.b])
        self.assertEqual(cfg['outbounds'][-1]['type'],'selector')
        self.assertEqual(cfg['route']['final'],'Best Selection')
        self.assertNotIn('inbounds',cfg)

    def test_distinct_ports(self):
        ports=available_ports(14)
        self.assertEqual(len(set(ports)),14)

    def test_endpoint_rotation(self):
        urls=['a','b','c']
        out=endpoint_order(urls,'00000001aaaa')
        self.assertEqual(out,['b','c','a'])

if __name__=='__main__':unittest.main()
