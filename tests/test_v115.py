"""Client-mode regression tests: scanner remains unchanged, no direct fallback."""
from __future__ import annotations
import json
import os
import socket
import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest.mock import patch, Mock

from iran_proxy_monitor import client
from iran_proxy_monitor.client import ClientManager, client_config, saved_shortlist_node
from iran_proxy_monitor.settings import Settings

PROXY={'type':'vless','tag':'original','server':'example.org','server_port':443,'uuid':'11111111-1111-1111-1111-111111111111'}


class ConfigTests(unittest.TestCase):
    def test_manual_is_only_loopback_and_selected_proxy(self):
        cfg=client_config(PROXY,'manual',20808)
        self.assertEqual(len(cfg['inbounds']),1)
        self.assertEqual(cfg['inbounds'][0]['type'],'mixed')
        self.assertEqual(cfg['inbounds'][0]['listen'],'127.0.0.1')
        self.assertEqual(cfg['route']['final'],'selected')
        self.assertEqual(cfg['outbounds'][0]['tag'],'selected')
        self.assertNotIn('direct',str(cfg['outbounds']))
        self.assertEqual(PROXY['tag'],'original')
        self.assertNotIn('auto_route',str(cfg))

    def test_system_only_differs_in_host_control_not_core(self):
        cfg=client_config(PROXY,'system',20808)
        self.assertEqual(cfg['inbounds'][0]['type'],'mixed')
        self.assertFalse(any(x.get('set_system_proxy') for x in cfg['inbounds']))

    def test_tun_has_strict_route_and_proxied_dns(self):
        cfg=client_config(PROXY,'tun',20808)
        tun=cfg['inbounds'][1]
        self.assertEqual(tun['type'],'tun')
        self.assertTrue(tun['auto_route'])
        self.assertTrue(tun['strict_route'])
        self.assertEqual(tun['dns_mode'],'hijack')
        self.assertTrue(cfg['route']['auto_detect_interface'])
        self.assertEqual(cfg['dns']['final'],'tunnel-dns')
        self.assertEqual(cfg['dns']['servers'][1]['detour'],'selected')

    def test_invalid_modes_ports_and_nonproxy_rejected(self):
        for mode in ('nope','auto','direct'):
            with self.assertRaises(ValueError):client_config(PROXY,mode,20808)
        for port in (0,80,65536):
            with self.assertRaises(ValueError):client_config(PROXY,'manual',port)
        for outbound in ({'type':'direct'},{'type':'block'},{'type':'selector'}):
            with self.assertRaises(ValueError):client_config(outbound,'manual',20808)

    def test_shortlist_reuses_same_first_node_and_rejects_untrusted_input(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d)
            (root/'best-overall-latest.json').write_text(json.dumps({'outbounds':[
                PROXY,{'type':'selector','tag':'Pick','outbounds':['original']}]}),'utf-8')
            name,out=saved_shortlist_node('best-overall',root)
            self.assertEqual(name,'original')
            self.assertEqual(out,PROXY)
            self.assertEqual(saved_shortlist_node('best-overall',root,1)[0],name)
            with self.assertRaises(ValueError):saved_shortlist_node('best-overall',root,2)
            out['server']='other'
            self.assertEqual(PROXY['server'],'example.org')
            with self.assertRaises(ValueError):saved_shortlist_node('../other',root)
            with self.assertRaises(FileNotFoundError):saved_shortlist_node('best-ping',root)

    def test_client_settings_do_not_change_scan_defaults(self):
        s=Settings()
        s.client_mode='system';s.client_listen_port=21000
        s.validate()
        self.assertEqual(s.speed_candidates,250)
        self.assertEqual(s.probe_processes,4)
        with self.assertRaises(ValueError):
            s.client_mode='invalid';s.validate()


class FakeJob:
    def close(self):pass

class FakeProxySwitch:
    def __init__(self):self.enabled=[];self.restored=0
    def enable(self,port):self.enabled.append(port)
    def restore(self):self.restored+=1

class FakeCore:
    def __init__(self,port):
        self.ended=False
        self.sock=socket.socket(socket.AF_INET,socket.SOCK_STREAM)
        self.sock.bind(('127.0.0.1',port));self.sock.listen(10)
        self.sock.settimeout(.2)
        self.thread=threading.Thread(target=self.listen,daemon=True)
        self.thread.start()
    def listen(self):
        while not self.ended:
            try:
                conn,_=self.sock.accept()
                conn.close()
            except socket.timeout:continue
            except OSError:break
    def poll(self):return 0 if self.ended else None
    def terminate(self):
        self.ended=True;self.sock.close()
    def wait(self,timeout=None):
        self.thread.join(timeout=timeout)
        return 0
    def kill(self):self.terminate()

class LifecycleTests(unittest.TestCase):
    def setUp(self):
        self.sock=socket.socket();self.sock.bind(('127.0.0.1',0))
        self.port=self.sock.getsockname()[1];self.sock.close()
        self.switch=FakeProxySwitch();self.manager=ClientManager(self.switch)
    def tearDown(self):self.manager.stop()
    def connect(self,mode='manual'):
        with patch.object(client,'find_singbox',return_value='fake-core'), \
             patch.object(client,'check_core',return_value=True), \
             patch.object(client.subprocess,'Popen',side_effect=lambda *a,**k:FakeCore(self.port)), \
             patch.object(client,'WindowsKillJob',return_value=FakeJob()):
            return self.manager.start('fake-core',PROXY,'Test Node',mode,self.port,startup_seconds=2)

    def test_manual_connected_then_stop_and_reuse(self):
        self.assertIn('CONNECTED',self.connect())
        self.assertTrue(self.manager.active)
        self.assertEqual(self.manager.mode,'manual')
        self.assertFalse(self.switch.enabled)
        self.assertEqual(self.manager.status().count('CONNECTED'),1)
        with self.assertRaises(RuntimeError):self.connect()
        self.manager.stop()
        self.assertFalse(self.manager.active)
        self.assertIn('CONNECTED',self.connect())

    def test_system_mode_applies_after_listener_ready_and_restores(self):
        self.assertIn('CONNECTED',self.connect('system'))
        self.assertEqual(self.switch.enabled,[self.port])
        self.assertEqual(self.manager.mode,'system')
        self.manager.stop()
        self.assertGreaterEqual(self.switch.restored,1)

    def test_core_check_failure_does_not_set_system_proxy(self):
        with patch.object(client,'find_singbox',return_value='fake-core'), \
             patch.object(client,'check_core',return_value=False):
            with self.assertRaises(RuntimeError):
                self.manager.start('fake-core',PROXY,'X','system',self.port)
        self.assertFalse(self.manager.active)
        self.assertFalse(self.switch.enabled)

    def test_tun_refuses_non_windows_early(self):
        if os.name=='nt': self.skipTest('Test on Linux only')
        with self.assertRaisesRegex(RuntimeError,'only on Windows'):
            self.manager.start('fake-core',PROXY,'X','tun',self.port)
        self.assertFalse(self.manager.active)

    def test_core_early_exit_is_reported_and_rolls_back(self):
        fail=Mock();fail.poll.return_value=1;fail.returncode=1
        with patch.object(client,'find_singbox',return_value='fake-core'), \
             patch.object(client,'check_core',return_value=True), \
             patch.object(client.subprocess,'Popen',return_value=fail), \
             patch.object(client,'WindowsKillJob',return_value=FakeJob()):
            with self.assertRaisesRegex(RuntimeError,'exited'):
                self.manager.start('fake-core',PROXY,'X','system',self.port,startup_seconds=.1)
        self.assertFalse(self.switch.enabled)

if __name__=='__main__':unittest.main()

class WindowsProxyRestoreTests(unittest.TestCase):
    def test_enable_and_exact_restore_without_overwriting_other_app(self):
        from iran_proxy_monitor import win_system_proxy as wp
        from types import SimpleNamespace
        # Windows registry is simulated; do not modify host settings.
        class FakeWinOS:
            name='nt'
            def __getattr__(self,key):return getattr(os,key)
        with tempfile.TemporaryDirectory() as d:
            original={'ProxyEnable':{'present':True,'value':0,'kind':4},
                      'ProxyServer':{'present':True,'value':'my-old-proxy:8899','kind':1}}
            live=dict(original)
            changes=[]
            def read():return dict(live),''
            def write(values):
                live.update(values)
                changes.append(dict(values))
            with patch.object(wp,'RESTORE_FILE',Path(d)/'restore.json'), \
                 patch.object(wp,'os',FakeWinOS()), \
                 patch.object(wp,'_read_values',side_effect=read), \
                 patch.object(wp,'_write_values',side_effect=write), \
                 patch.object(wp,'_pid_alive',return_value=False):
                switch=wp.WindowsProxySwitch()
                switch.enable(20808)
                self.assertEqual(live['ProxyServer']['value'],'127.0.0.1:20808')
                self.assertTrue(wp.RESTORE_FILE.exists())
                switch.restore()
                self.assertEqual(live,original)
                self.assertFalse(wp.RESTORE_FILE.exists())
                switch.enable(20808)
                # Karing takes ownership while client was connected.
                live['ProxyServer']={'present':True,'value':'127.0.0.1:3067','kind':1}
                switch.restore()
                self.assertEqual(live['ProxyServer']['value'],'127.0.0.1:3067')
                self.assertFalse(wp.RESTORE_FILE.exists())

    def test_reject_pac_to_avoid_silent_wrong_system_proxy(self):
        from iran_proxy_monitor import win_system_proxy as wp
        class FakeWinOS:
            name='nt'
            def __getattr__(self,key):return getattr(os,key)
        with tempfile.TemporaryDirectory() as d, \
             patch.object(wp,'RESTORE_FILE',Path(d)/'restore.json'), \
             patch.object(wp,'os',FakeWinOS()), \
             patch.object(wp,'_read_values',return_value=({},'https://pac.example/script.pac')):
            with self.assertRaisesRegex(RuntimeError,'PAC'):
                wp.WindowsProxySwitch().enable(20808)
            self.assertFalse(wp.RESTORE_FILE.exists())
