"""IRAN REMAINS CONNECTED v1.1: adaptive dashboard and exclusive monitor controls.

The tests use Tk's actual geometry engine, not fake widgets.  They don't
require Internet access or sing-box to run.
"""
from __future__ import annotations
import tkinter as tk
from pathlib import Path
from unittest import TestCase
from unittest.mock import patch
from iran_proxy_monitor import __version__
from iran_proxy_monitor.gui import App


class TkAppCase(TestCase):
    def setUp(self):
        self.root=tk.Tk()
        self.app=App(self.root)
    def tearDown(self):
        try:
            self.app.close()
            self.root.update_idletasks()
        except tk.TclError:
            pass
        try:self.root.destroy()
        except tk.TclError:pass

    def size(self,width,height):
        self.root.geometry(f'{width}x{height}')
        self.root.update_idletasks();self.root.update()

class ResponsiveDashboardTests(TkAppCase):
    def test_fullscreen_layout_expands_table_and_hides_dashboard_scroll(self):
        self.size(1600,960)
        self.assertFalse(self.app._dashboard_scroll_visible)
        self.assertFalse(self.app.dashboard_scroll.winfo_ismapped())
        self.assertGreaterEqual(self.app.results_tabs.winfo_height(),200)
        self.assertEqual(tuple(round(x,2) for x in self.app.dashboard_canvas.yview()),(0.0,1.0))
        self.assertEqual(self.app.footer_bar.winfo_rooty()+self.app.footer_bar.winfo_height(),
                         self.root.winfo_rooty()+self.root.winfo_height())

    def test_ordinary_window_does_not_require_outer_scroll(self):
        self.size(1380,900)
        self.assertFalse(self.app._dashboard_scroll_visible)
        self.assertGreaterEqual(self.app.results_tabs.winfo_height(),150)

    def test_small_window_scrolls_by_mouse_wheel_over_buttons(self):
        self.size(1060,700)
        self.assertTrue(self.app._dashboard_scroll_visible)
        self.app.dashboard_canvas.yview_moveto(0)
        self.root.update()
        start=self.app.dashboard_canvas.yview()[0]
        self.app.monitor_buttons['Update subscription'].event_generate('<MouseWheel>',delta=-120)
        self.root.update()
        self.assertGreater(self.app.dashboard_canvas.yview()[0],start)
        footer=self.app.footer_bar
        self.assertLessEqual(footer.winfo_y()+footer.winfo_height(),self.root.winfo_height()+1)

    def test_tree_mouse_wheel_does_not_scroll_outer_dashboard(self):
        self.size(1060,700)
        self.app.dashboard_canvas.yview_moveto(0)
        self.root.update()
        for i in range(50):
            self.app.tree.insert('','end',values=(i,)+('x',)*(len(self.app.tree['columns'])-1))
        start=self.app.dashboard_canvas.yview()[0]
        self.app.tree.event_generate('<MouseWheel>',delta=-120)
        self.root.update()
        self.assertAlmostEqual(self.app.dashboard_canvas.yview()[0],start,places=3)

    def test_advanced_controls_reopen_without_losing_values(self):
        self.size(1380,900)
        self.assertFalse(self.app.advanced_frame.winfo_ismapped())
        self.app.probe_processes.set('3')
        self.app.toggle_advanced()
        self.root.update()
        self.assertTrue(self.app.advanced_frame.winfo_ismapped())
        self.assertTrue(self.app._dashboard_scroll_visible)
        self.assertIn('▾',self.app.advanced_toggle.cget('text'))
        self.app.toggle_advanced()
        self.root.update()
        self.assertFalse(self.app.advanced_frame.winfo_ismapped())
        self.assertFalse(self.app._dashboard_scroll_visible)
        self.assertEqual(self.app.probe_processes.get(),'3')
        self.assertTrue(self.app.cached_only is not None)

    def test_version_and_installer_versions_match(self):
        self.assertEqual(__version__,'1.1')
        path=Path(__file__).resolve().parent.parent/'release'/'IranProxyMonitor.iss'
        self.assertIn('#define MyAppVersion "1.1"',path.read_text())
        self.assertIn(f'v{__version__}',
                      self.app.footer_bar.winfo_children()[1].winfo_children()[1].cget('text'))

class MonitorButtonInterlockTests(TkAppCase):
    def drain_queue(self):
        self.root.after_cancel(self.app._poll_after_id)
        self.app.poll()

    def button_disabled(self,label):
        return 'disabled' in self.app.monitor_buttons[label].state()

    def test_idle_all_buttons_available(self):
        for label in self.app.monitor_buttons:
            self.assertFalse(self.button_disabled(label),label)

    def test_updating_feed_locks_all_other_actions_until_ready(self):
        self.app.running=True
        self.app._update_monitor_buttons()
        for label in ('Update subscription','Run one cycle','Start auto monitoring','Run once + auto'):
            self.assertTrue(self.button_disabled(label),label)
        self.assertFalse(self.button_disabled('Stop'))
        self.app.stop()
        self.assertTrue(self.button_disabled('Run one cycle'))  # wait for worker to exit
        self.app.queue.put(('ready',None))
        self.drain_queue()
        self.assertFalse(self.button_disabled('Run one cycle'))
        self.assertFalse(self.button_disabled('Update subscription'))

    def test_auto_monitor_arms_timer_without_immediate_scan(self):
        with patch.object(self.app,'save',return_value=True):
            self.app.start()
        self.assertTrue(self.app.monitor_enabled)
        self.assertFalse(self.app.running)
        for label in ('Update subscription','Run one cycle','Start auto monitoring','Run once + auto'):
            self.assertTrue(self.button_disabled(label),label)
        self.assertFalse(self.button_disabled('Stop'))
        self.app.stop()
        self.assertFalse(self.app.monitor_enabled)
        for label in ('Update subscription','Run one cycle','Start auto monitoring','Run once + auto'):
            self.assertFalse(self.button_disabled(label),label)

    def test_run_once_and_auto_prevents_other_actions(self):
        self.app.settings.subscription_url='https://example.invalid/feed'
        self.app.url.set('https://example.invalid/feed')
        with patch.object(self.app,'save',return_value=True),patch.object(self.app,'worker',return_value=None):
            self.app.run_and_monitor()
        self.assertTrue(self.app.running)
        self.assertTrue(self.app.monitor_enabled)
        self.assertTrue(self.button_disabled('Update subscription'))
        self.assertTrue(self.button_disabled('Run one cycle'))
        self.assertTrue(self.button_disabled('Run once + auto'))
        self.app.stop()
        self.app.queue.put(('ready',None));self.drain_queue()
        self.assertFalse(self.button_disabled('Update subscription'))

    def test_normal_cycle_returns_to_idle_on_completion(self):
        self.app.settings.subscription_url='https://example.invalid/feed'
        self.app.url.set('https://example.invalid/feed')
        with patch.object(self.app,'save',return_value=True),patch.object(self.app,'worker',return_value=None):
            self.app.run_once()
        self.assertTrue(self.button_disabled('Update subscription'))
        self.app.queue.put(('ready',None));self.drain_queue()
        self.assertFalse(self.app.running)
        self.assertFalse(self.button_disabled('Update subscription'))

class FrozenInstallerCoreTests(TestCase):
    def test_stale_development_core_path_is_replaced_with_bundled_core(self):
        import tempfile
        import sys
        from iran_proxy_monitor.settings import Settings
        with tempfile.TemporaryDirectory() as td:
            dist=Path(td)
            core=dist/'bin'/'sing-box.exe'
            core.parent.mkdir()
            core.write_bytes(b'fake-binary')
            fake_exe=dist/'IranRemainsConnected.exe'
            with patch.object(sys,'frozen',True,create=True),\
                 patch.object(sys,'executable',str(fake_exe)),\
                 patch('iran_proxy_monitor.gui.Settings.load',return_value=Settings(singbox_path=r'C:\old-source-zip\bin\sing-box.exe')):
                root=tk.Tk()
                app=App(root)
                try:
                    self.assertEqual(app.settings.singbox_path,str(core))
                finally:
                    app.close()
                    try:root.destroy()
                    except tk.TclError:pass
