import base64
import json
import unittest
from iran_proxy_monitor.parser import parse_subscription,link_node

class ParserTests(unittest.TestCase):
    def test_vless_reality_ignores_spider_hint_but_preserves_raw(self):
        s='vless://123e4567-e89b-12d3-a456-426614174000@example.org:443?encryption=none&security=reality&pbk=abcdef&sid=1234&sni=www.example.org&fp=chrome&type=ws&host=cdn.example.org&path=%2Fweb&spx=%2F#Test%20Node'
        n=link_node(s)
        self.assertTrue(n.supported,n.problems)
        self.assertEqual(n.outbound['tls']['reality']['public_key'],'abcdef')
        self.assertEqual(n.outbound['transport']['headers']['Host'],'cdn.example.org')
        self.assertEqual(n.outbound['transport']['path'],'/web')
        self.assertIn('spx',n.warnings[0]);self.assertEqual(n.source_text,s)

    def test_base64_uri_list_and_dedup(self):
        s='trojan://secret@example.net:443?sni=example.net#A\nss://YWVzLTI1Ni1nY206cGFzcw@example.org:8388#S\n'
        b=base64.urlsafe_b64encode((s+s.splitlines()[0]+'\n').encode()).decode().rstrip('=')
        r=parse_subscription(b)
        self.assertEqual(r.total,3)
        self.assertEqual(r.duplicates,1)
        self.assertEqual(r.usable,2)

    def test_clash_and_unsupported_not_silent(self):
        s='''proxies:
  - name: Good VLESS
    type: vless
    server: sample.org
    port: 443
    uuid: 123e4567-e89b-12d3-a456-426614174000
    tls: true
    reality-opts:
      public-key: xyz
      short-id: '12'
  - name: Experimental
    type: vless
    server: sample.org
    port: 443
    uuid: 123e4567-e89b-12d3-a456-426614174000
    network: xhttp
  - name: Experimental2
    type: unknownprotocol
    server: sample.org
    port: 443
'''
        r=parse_subscription(s)
        self.assertEqual(r.total,3)
        self.assertEqual(r.usable,1)
        self.assertEqual(r.unsupported,2)
        self.assertEqual(len(r.nodes),3)

    def test_vmess(self):
        item={'v':'2','ps':'VMess A','add':'example.com','port':'443','id':'123e4567-e89b-12d3-a456-426614174000',
              'aid':0,'net':'ws','tls':'tls','host':'www.example.com','path':'/vm'}
        uri='vmess://'+base64.urlsafe_b64encode(json.dumps(item).encode()).decode().rstrip('=')
        n=link_node(uri)
        self.assertTrue(n.supported)
        self.assertEqual(n.outbound['transport']['path'],'/vm')

    def test_singbox_json(self):
        s={'outbounds':[{'type':'shadowsocks','tag':'a','server':'1.2.3.4','server_port':8388,
                         'method':'aes-256-gcm','password':'secret'},
                         {'type':'direct','tag':'direct'}]}
        r=parse_subscription(json.dumps(s))
        self.assertEqual(r.usable,1)
        self.assertEqual(r.unsupported,1)

    def test_xray_json(self):
        s={'outbounds':[{'tag':'X','protocol':'vless','settings':{'vnext':[
          {'address':'x.example','port':443,'users':[{'id':'123e4567-e89b-12d3-a456-426614174000','flow':'xtls-rprx-vision'}]}]},
          'streamSettings':{'security':'reality','realitySettings':{'serverName':'example.com','publicKey':'key','shortId':'a1'},'network':'tcp'}}]}
        r=parse_subscription(json.dumps(s))
        self.assertEqual(r.usable,1,r.errors)
        self.assertEqual(r.nodes[0].outbound['tls']['reality']['public_key'],'key')

    def test_large_feed_no_fixed_limit(self):
        lines=['vless://123e4567-e89b-12d3-a456-426614174000@node%d.example:443?security=tls&sni=example.com#Node%d'%(i,i)
               for i in range(12050)]
        r=parse_subscription('\n'.join(lines))
        self.assertEqual(r.usable,12050)
        self.assertEqual(r.total,12050)

    def test_invalid_different_records_not_collapsed(self):
        r=parse_subscription('nonsense://A\nnonsense://B')
        self.assertEqual(r.unsupported,2)
        self.assertEqual(r.duplicates,0)

if __name__=='__main__':unittest.main()
