"""Offline and integration tests for v1.0.12 profile/proxy improvements."""
from __future__ import annotations
import io
import json
import os
import socket
import struct
import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import patch
from iran_proxy_monitor import bpf, exporter, feed_proxy, settings
from iran_proxy_monitor.models import Node


class BpfTests(unittest.TestCase):
    def make_nodes(self):
        return [Node(name='Test '+str(i), protocol='http',
                     outbound={'type':'http','server':f'{i}.example.org','server_port':8080},
                     source_kind='link',source_text=f'http://{i}.example.org:8080') for i in (1,2,3)]

    def test_multiple_nodes_in_single_bpf(self):
        nodes=self.make_nodes()
        config=exporter.shortlist_config(nodes)
        android=exporter.android_profile_config(config)
        binary=bpf.create_bpf('Three Nodes', android)
        name, decoded=bpf.decode_bpf(binary)
        self.assertEqual(name,'Three Nodes')
        self.assertEqual(binary[:4],b'\x03\x01\x1f\x8b')
        self.assertEqual(decoded['outbounds'], config['outbounds'])
        self.assertEqual(len([o for o in decoded['outbounds'] if o['type']=='http']),3)
        self.assertEqual(decoded['inbounds'][0]['type'],'tun')
        self.assertEqual(decoded['route']['final'], 'Best Selection')

    def test_varint_utf8_name(self):
        name='آزمایش '+('A'*200)
        payload=bpf.create_bpf(name,{'outbounds':[]})
        result,config=bpf.decode_bpf(payload)
        self.assertEqual(result,name)
        self.assertEqual(config['outbounds'],[])

    def test_invalid_bpf_rejected(self):
        with self.assertRaises(ValueError):bpf.decode_bpf(b'\x03\x01x')
        with self.assertRaises(ValueError):bpf.create_bpf('', {'outbounds':[]})

    def test_each_export_has_matching_bpf_json_and_uri_list(self):
        with tempfile.TemporaryDirectory() as temp, patch.object(exporter,'OUT',Path(temp)), patch.object(exporter,'check_core',return_value=True):
            for kind in ('best-download-speed','best-ping','best-overall'):
                result=exporter.export_shortlist(self.make_nodes(),kind,'dummy.exe')
                json_cfg=json.loads(Path(result['json']).read_text())
                name,mobile=bpf.decode_bpf(Path(result['bpf']).read_bytes())
                self.assertEqual(mobile['outbounds'],json_cfg['outbounds'])
                self.assertEqual(len(Path(result['links']).read_text().strip().splitlines()),3)
                self.assertTrue(Path(result['bpf']).is_file())

    def test_invalid_mobile_config_keeps_prior_json_and_bpf(self):
        with tempfile.TemporaryDirectory() as temp, patch.object(exporter,'OUT',Path(temp)):
            output=Path(temp)
            original_json=output/'best-overall-latest.json'
            original_bpf=output/'best-overall-latest.bpf'
            original_json.write_text('old json');original_bpf.write_bytes(b'old bpf')
            with patch.object(exporter,'check_core',side_effect=[True,False]):
                with self.assertRaises(RuntimeError):
                    exporter.export_shortlist(self.make_nodes(),'best-overall','dummy.exe')
            self.assertEqual(original_json.read_text(),'old json')
            self.assertEqual(original_bpf.read_bytes(),b'old bpf')


class SettingsTests(unittest.TestCase):
    def test_manual_proxy_inputs_validated(self):
        self.assertIsNone(feed_proxy.validate_proxy_settings('manual-socks5','127.0.0.1',3067))
        for port in (0,65536):
            with self.assertRaises(ValueError):
                feed_proxy.validate_proxy_settings('manual-http','127.0.0.1',port)
        with self.assertRaises(ValueError):
            feed_proxy.validate_proxy_settings('manual-socks5','https://evil',3000)

    def test_password_never_persisted(self):
        with tempfile.TemporaryDirectory() as temp, patch.object(settings,'DATA_DIR',Path(temp)):
            value=settings.Settings(subscription_proxy_mode='manual-socks5',
                  subscription_proxy_host='127.0.0.1',subscription_proxy_port=3067,
                  subscription_proxy_username='sensitive-name',subscription_proxy_password='SECRET')
            value.save()
            raw=(Path(temp)/'settings.json').read_text()
            self.assertNotIn('SECRET',raw)
            self.assertNotIn('sensitive-name',raw)
            self.assertEqual(settings.Settings.load().subscription_proxy_password,'')
            self.assertEqual(settings.Settings.load().subscription_proxy_mode,'manual-socks5')

    def test_system_direct_http_socks_opener_creation(self):
        for mode in feed_proxy.MODES:
            result=feed_proxy.build_feed_opener(mode,'127.0.0.1',3067)
            self.assertTrue(hasattr(result,'open'))


class Socks5IntegrationTests(unittest.TestCase):
    def test_http_subscription_through_socks5_with_remote_dns(self):
        ready=threading.Event();details={}
        listener=socket.socket();listener.bind(('127.0.0.1',0));listener.listen(1)
        port=listener.getsockname()[1]
        def server():
            ready.set()
            try:
                conn,_=listener.accept()
                with conn:
                    self.assertEqual(feed_proxy._read_exact(conn,2),b'\x05\x01')
                    self.assertEqual(feed_proxy._read_exact(conn,1),b'\x00')
                    conn.sendall(b'\x05\x00')
                    self.assertEqual(feed_proxy._read_exact(conn,4),b'\x05\x01\x00\x03')
                    hostname_len=feed_proxy._read_exact(conn,1)[0]
                    details['host']=feed_proxy._read_exact(conn,hostname_len).decode()
                    details['port']=int.from_bytes(feed_proxy._read_exact(conn,2),'big')
                    conn.sendall(b'\x05\x00\x00\x01\x7f\x00\x00\x01\x00\x50')
                    request=conn.recv(4096)
                    self.assertIn(b'GET /feed HTTP/1.1',request)
                    body=b'vless://test-entry\n'
                    conn.sendall(b'HTTP/1.1 200 OK\r\nContent-Length: '+str(len(body)).encode()+b'\r\nConnection: close\r\n\r\n'+body)
            finally:listener.close()
        thread=threading.Thread(target=server,daemon=True);thread.start()
        ready.wait(2)
        response=feed_proxy.build_feed_opener('manual-socks5','127.0.0.1',port).open(
            'http://example.invalid:80/feed', timeout=3)
        with response:self.assertEqual(response.read(),b'vless://test-entry\n')
        thread.join(3)
        self.assertEqual(details['host'],'example.invalid')
        self.assertEqual(details['port'],80)

    def test_socks_username_password_handshake(self):
        left,right=socket.socketpair()
        def reply():
            try:
                self.assertEqual(feed_proxy._read_exact(right,2),b'\x05\x02')
                self.assertEqual(feed_proxy._read_exact(right,2),b'\x00\x02')
                right.sendall(b'\x05\x02')
                self.assertEqual(feed_proxy._read_exact(right,2),b'\x01\x04')
                self.assertEqual(feed_proxy._read_exact(right,4),b'user')
                self.assertEqual(feed_proxy._read_exact(right,1),b'\x04')
                self.assertEqual(feed_proxy._read_exact(right,4),b'pass')
                right.sendall(b'\x01\x00')
                header=feed_proxy._read_exact(right,5)
                self.assertEqual(header,b'\x05\x01\x00\x03\x0b')
                self.assertEqual(feed_proxy._read_exact(right,11),b'example.org')
                self.assertEqual(int.from_bytes(feed_proxy._read_exact(right,2),'big'),443)
                right.sendall(b'\x05\x00\x00\x01\x7f\x00\x00\x01\x00\x00')
            finally:right.close()
        thread=threading.Thread(target=reply,daemon=True);thread.start()
        feed_proxy.socks5_connect(left,'example.org',443,'user','pass')
        left.close();thread.join(3)



class AdditionalReleaseTests(unittest.TestCase):
    def test_rebuild_bpf_from_previous_json_without_scanning(self):
        with tempfile.TemporaryDirectory() as temp, patch.object(exporter,'OUT',Path(temp)), patch.object(exporter,'check_core',return_value=True):
            kind='best-overall'
            cfg=exporter.shortlist_config(BpfTests().make_nodes())
            original=json.dumps(cfg)
            (Path(temp)/f'{kind}-latest.json').write_text(original)
            out=exporter.rebuild_android_bpf_from_saved_json('dummy.exe')
            self.assertIn(kind,out)
            self.assertEqual((Path(temp)/f'{kind}-latest.json').read_text(),original)
            _,mobile=bpf.decode_bpf(Path(out[kind]).read_bytes())
            self.assertEqual(mobile['outbounds'],cfg['outbounds'])

    def test_no_saved_shortlists_does_not_produce_empty_bpf(self):
        with tempfile.TemporaryDirectory() as temp, patch.object(exporter,'OUT',Path(temp)):
            with self.assertRaises(FileNotFoundError):
                exporter.rebuild_android_bpf_from_saved_json('dummy.exe')

    def test_cached_only_checkbox_settings_persist(self):
        with tempfile.TemporaryDirectory() as temp, patch.object(settings,'DATA_DIR',Path(temp)):
            value=settings.Settings(use_cached_subscription_for_tests=True)
            value.save()
            self.assertTrue(settings.Settings.load().use_cached_subscription_for_tests)

    def test_cached_only_run_does_not_fetch_remote(self):
        from iran_proxy_monitor import monitor
        from iran_proxy_monitor.parser import parse_subscription
        report=parse_subscription(b'http://example.org:8080#test\n')
        local=settings.Settings(subscription_url='https://example.org/feed',
                                use_cached_subscription_for_tests=True)
        import threading
        with patch.object(monitor,'load_report',return_value=(report,'cached-same-source')) as mocked:
            stop=threading.Event(); stop.set()
            stats=monitor._unlocked_run_cycle(local,stop)
            self.assertEqual(stats['subscription'],'cached-same-source')
            self.assertTrue(mocked.call_args.kwargs['cache_only'])
        with patch.object(monitor,'load_report',return_value=(report,'fresh')) as mocked:
            stats=monitor._unlocked_run_cycle(local,threading.Event(),update_only=True)
            self.assertFalse(mocked.call_args.kwargs['cache_only'])

    def test_public_installer_source_and_build_workflow_present(self):
        root=Path(__file__).resolve().parents[1]
        self.assertIn('Python', (root/'release/README.md').read_text())
        workflow=(root/'.github/workflows/windows-release.yml').read_text()
        self.assertIn('windows-latest',workflow)
        self.assertIn('upload-artifact',workflow)
        self.assertIn('ISCC.exe',(root/'release/build-windows.ps1').read_text())
        self.assertIn('PrivilegesRequired=lowest',(root/'release/IranProxyMonitor.iss').read_text())

if __name__=='__main__': unittest.main()
