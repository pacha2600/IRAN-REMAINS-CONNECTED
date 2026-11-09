"""Live Windows Tkinter dashboard. Background network workers never call Tk directly."""
from __future__ import annotations
import copy
import json
import os
import queue
import subprocess
import threading
import time
from datetime import datetime
from pathlib import Path
import sys
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
from .settings import Settings, DATA_DIR, split_subscription_sources
from . import __version__
from .models import Node
from .monitor import (run_cycle, persist_stats, read_stats, CycleBusy, OperationCancelled, NoUsableMeasurements,
                      active_cycle_info, request_cancel_active_cycle, subscription_fingerprint, read_working_snapshot)
from .exporter import OUT
from .diagnostics import LOG_DIR, LOG_FILE, CycleFailure, record_failure, event
from .tooltips import Tooltips
from .scheduler import AutoScheduler
from .network import outbound_route_present
from .client import (ClientManager, saved_shortlist_node, connection_warnings,
                     client_config, is_administrator)
from .security import assess_outbound
from .engine import check_core, find_singbox
from .connection_history import remember_connection, recent_connections, clear_connections
from .scan_usage import daily_payload_bytes
from .win_system_proxy import WindowsProxySwitch
from .compare import compare_node, format_comparison

BG='#101827'; PANEL='#192537'; TEXT='#e4edf6'; MUTED='#a4b3c5'; CYAN='#5dd4d7'
COLUMNS=('rank','name','protocol','encryption','security','latency','download','flow','sample','reliability','confirmed','status')
RECENT_COLUMNS=('connected_at','mode')+COLUMNS
COLUMN_LABELS={
    'rank':'#','name':'Node','protocol':'Protocol','encryption':'Encryption',
    'security':'Security /100','latency':'HTTPS latency (ms)','download':'Avg Mbps',
    'flow':'Flow Mbps','sample':'Window (s)','reliability':'Reliability',
    'confirmed':'Stable','status':'Status','connected_at':'Connected at','mode':'Mode'}
COLUMN_WIDTHS={
    'rank':50,'name':235,'protocol':85,'encryption':188,'security':105,
    'latency':138,'download':100,'flow':102,'sample':86,'reliability':82,
    'confirmed':75,'status':186,'connected_at':152,'mode':99}



def copyable_config(node: Node) -> str:
    """Exact original share URI when available; otherwise a sing-box outbound JSON.

    Do NOT reconstruct VLESS/VMess URIs from translated options: that can drop
    transport and TLS parameters. JSON is explicitly a different import format.
    """
    if node.source_kind=='link' and '://' in node.source_text:
        return node.source_text.strip()
    if node.outbound:
        return json.dumps({'outbounds':[node.outbound]},indent=2,ensure_ascii=False)
    return node.source_text.strip()


class App:
    def __init__(self,root):
        self.root=root
        self.root.title('IRAN REMAINS CONNECTED  •  Scanner & VPN Client')
        # The icon is applied twice on Windows.  Python's Tk title-bar window
        # can be wrapped by a native HWND, and iconbitmap alone does not reliably
        # update that wrapper's small and large icons on all Tk/Windows builds.
        self._windows_icon_handles=[]
        self._icon_after_id=None
        self._icon_retry_count=0
        self._icon_map_binding=None
        asset_root=Path(getattr(sys,'_MEIPASS',Path(__file__).resolve().parent.parent))
        self._icon_ico=asset_root/'assets'/'iran-remains-connected.ico'
        self._icon_png=asset_root/'assets'/'iran-remains-connected.png'
        self.app_icon=None
        try:
            if self._icon_png.is_file():
                self.app_icon=tk.PhotoImage(file=str(self._icon_png))
                self.root.iconphoto(True,self.app_icon)
            if sys.platform=='win32' and self._icon_ico.is_file():
                self.root.iconbitmap(default=str(self._icon_ico))
                # Windows/Tk can create its decorated top-level HWND *after*
                # Tk startup; <Map> retries when the real taskbar window exists.
                self._icon_map_binding=self.root.bind('<Map>',self._on_icon_map,add='+')
                self._icon_after_id=self.root.after(100,self._apply_windows_icon)
        except (OSError,tk.TclError) as exc:
            event('application-icon-warning',error=type(exc).__name__)
        self.root.geometry('1380x900'); self.root.minsize(1020,680)
        root.configure(bg=BG)
        self.settings=Settings.load()
        # A published PyInstaller install includes its own core. Upgrade users
        # may have a stale path to a previous source ZIP in settings.json;
        # prefer the bundled core when that saved path no longer exists.
        if getattr(sys,'frozen',False):
            bundled_core=Path(sys.executable).resolve().parent/'bin'/'sing-box.exe'
            if bundled_core.is_file() and (not self.settings.singbox_path or
                                           not Path(self.settings.singbox_path).is_file()):
                self.settings.singbox_path=str(bundled_core)
        self.connection = ClientManager()
        self.client_busy = False
        self.client_disconnect_after_busy = False
        self.client_thread = None
        try: WindowsProxySwitch().recover_stale()
        except Exception: pass  # Leave user settings untouched on recovery error.
        self.displayed_source_id=None  # source of the results currently on screen, if verified
        self.queue=queue.Queue();self.cancel=threading.Event()
        self.running=False;self.comparing=False;self.monitor_enabled=False;self.schedule=AutoScheduler();self.worker_thread=None
        self.nodes_by_id={};self.row_state={};self.rows_generation=0
        self.pending_rows=[];self.table_sort='latency';self.reverse=False
        self.working_table_sort='latency';self.working_reverse=False
        self._pending_connection=None
        self._active_connection=None  # (outbound, name, last-measured metrics)
        self._deferred_mode=None
        self.working_ids=set();self._last_traffic_refresh=0.0
        self._populate_after_id=None
        self.sort_pending=False;self.last_sort=0
        self.live_passed=0;self.live_downloads=0;self.live_speed_attempts=0
        self.live_speed_seen=set();self.live_top=0.0
        self.style=ttk.Style();self.style.theme_use('clam')
        self.style.configure('TFrame',background=BG)
        self.style.configure('Footer.TFrame',background='#0b1524')
        self.style.configure('Footer.TLabel',background='#0b1524',foreground=TEXT,font=('Segoe UI',9))
        self.style.configure('FooterMuted.TLabel',background='#0b1524',foreground=MUTED,font=('Segoe UI',9))
        self.style.configure('FooterVersion.TLabel',background='#0b1524',foreground=CYAN,font=('Segoe UI Semibold',9))
        self.style.configure('Panel.TFrame',background=PANEL)
        self.style.configure('TLabel',background=BG,foreground=TEXT,font=('Segoe UI',10))
        self.style.configure('Muted.TLabel',background=BG,foreground=MUTED,font=('Segoe UI',9))
        self.style.configure('Title.TLabel',background=BG,foreground=TEXT,font=('Segoe UI Semibold',18))
        self.style.configure('Card.TLabel',background=PANEL,foreground=TEXT,font=('Segoe UI Semibold',15))
        self.style.configure('CardSmall.TLabel',background=PANEL,foreground=MUTED,font=('Segoe UI',9))
        self.style.configure('TButton',font=('Segoe UI',9),padding=(7,3))
        self.style.configure('Accent.TButton',background='#176d9c',foreground='#ffffff',padding=(9,3))
        self.style.map('Accent.TButton',background=[('active','#2588c2')])
        self.style.configure('Treeview',background=PANEL,fieldbackground=PANEL,foreground=TEXT,
                             font=('Segoe UI',9),rowheight=25,borderwidth=0)
        self.style.configure('Treeview.Heading',background='#2b3b50',foreground=TEXT,
                             font=('Segoe UI Semibold',9))
        self.style.map('Treeview',background=[('selected','#28617a')])
        self.root.protocol('WM_DELETE_WINDOW',self.close)
        self.tip=Tooltips(root)
        self.make_ui();self.present(read_stats(),update_table=False)
        self.load_previous_working()
        owner=active_cycle_info()
        if owner:
            self.status.set(f'An operation in process {owner["pid"]} may still be running. Stop requests cancellation; new tests must wait.')
        self._poll_after_id=self.root.after(100,self.poll)

    def _on_icon_map(self,_event=None):
        """Reapply after Windows creates/maps the decorated top-level HWND."""
        if self._icon_after_id is None and self._icon_retry_count < 4:
            try:self._icon_after_id=self.root.after(100,self._apply_windows_icon)
            except tk.TclError:pass

    def _apply_windows_icon(self):
        """Apply real .ico resources to Tk's decorated HWND and Windows class.

        iconphoto/iconbitmap alone do not reliably update the Windows 11
        taskbar icon in a frozen Tkinter GUI. Locate the topmost ancestor,
        because winfo_id can refer to an undecorated Tk child window.
        """
        self._icon_after_id=None
        if sys.platform!='win32':return
        if not self._icon_ico.is_file():
            event('application-icon-warning',error='BundledIconMissing')
            return
        try:
            from .windows_icon import apply_windows_icon
            result=apply_windows_icon(int(self.root.winfo_id()),str(self._icon_ico))
            # Retain the HICON objects for the lifetime of the process:
            # WM_SETICON and class icon properties borrow, not own, them.
            self._windows_icon_handles.extend(result['handles'])
            if not result['applied']:
                event('application-icon-warning',error='NativeIconNotApplied')
            if self._icon_retry_count == 0:
                event('application-icon-applied',windows=result['windows'],handles=len(result['handles']))
            self._icon_retry_count+=1
            if self._icon_retry_count < 3:
                self._icon_after_id=self.root.after(700,self._apply_windows_icon)
        except (OSError,AttributeError,ValueError,tk.TclError) as exc:
            event('application-icon-warning',error=type(exc).__name__)

    def toggle_advanced(self):
        if self.advanced_expanded.get():
            self.advanced_frame.pack_forget()
            self.advanced_expanded.set(False)
            self.advanced_toggle.configure(text='Advanced scan settings ▸')
        else:
            self.advanced_frame.pack(fill='x',before=self.advanced_frame_next,pady=(1,3))
            self.advanced_expanded.set(True)
            self.advanced_toggle.configure(text='Advanced scan settings ▾')
        self._fit_dashboard()

    def _update_monitor_buttons(self):
        """Exclusive monitor actions; Stop stays usable during cancellation."""
        buttons=getattr(self,'monitor_buttons',None)
        if not buttons:return
        locked=self.running or self.monitor_enabled
        for label,widget in buttons.items():
            widget.state(['!disabled'] if label=='Stop' or not locked else ['disabled'])
        # Stop is useful for an active scan/auto timer; it can also signal a
        # cycle owned by a different process, so leave it enabled at idle.

    @staticmethod
    def _section_line(parent,label,top=2):
        row=ttk.Frame(parent);row.pack(fill='x',pady=(top,5))
        ttk.Label(row,text=label,foreground=CYAN,font=('Segoe UI Semibold',9)).pack(side='left',padx=(0,12))
        ttk.Separator(row,orient='horizontal').pack(side='left',fill='x',expand=True,pady=(1,0))

    def make_ui(self):
        # Pack bottom first. Even when the results notebook is squeezed by a
        # non-maximized window the message, usage totals and version stay visible.
        self.footer=tk.StringVar(value='No cycle has been run yet.')
        self.scan_usage_text=tk.StringVar(value='Scan HTTP ≥ 0.000 MiB  |  Feed 0.000  Latency 0.000  Speed 0.000  Baseline 0.000')
        self.scan_live={'feed':0,'latency':0,'speed':0,'baseline':0}
        self._seen_latency=set();self._seen_speed=set()
        self.footer_bar=ttk.Frame(self.root,style='Footer.TFrame',padding=(12,5,12,6))
        self.footer_bar.pack(side='bottom',fill='x')
        ttk.Label(self.footer_bar,textvariable=self.footer,style='Footer.TLabel',anchor='w').pack(fill='x')
        usage_row=ttk.Frame(self.footer_bar,style='Footer.TFrame')
        usage_row.pack(fill='x',pady=(2,0))
        ttk.Label(usage_row,textvariable=self.scan_usage_text,style='FooterMuted.TLabel').pack(side='left')
        ttk.Label(usage_row,text=f'IRAN REMAINS CONNECTED  v{__version__}',style='FooterVersion.TLabel').pack(side='right')
        ttk.Separator(self.root,orient='horizontal').pack(side='bottom',fill='x')
        # Responsive viewport: expand the results table to the visible height
        # when possible; allow scrolling only if content cannot fit.
        # Canvas viewport: all controls + three tables remain reachable when
        # users unmaximize the window or work at 720p/125%-DPI. Footer is never
        # inside the viewport, so scan messages cannot be pushed off-screen.
        viewport=ttk.Frame(self.root)
        viewport.pack(side='top',fill='both',expand=True)
        self.dashboard_scroll=ttk.Scrollbar(viewport,orient='vertical')
        self.dashboard_scroll.pack(side='right',fill='y')
        self.dashboard_canvas=tk.Canvas(viewport,bg=BG,highlightthickness=0,borderwidth=0,
                                        yscrollcommand=self.dashboard_scroll.set)
        self.dashboard_canvas.pack(side='left',fill='both',expand=True)
        self.dashboard_scroll.configure(command=self.dashboard_canvas.yview)
        main=ttk.Frame(self.dashboard_canvas,padding=(11,7,11,5))
        self.dashboard_main=main
        self.dashboard_window=self.dashboard_canvas.create_window((0,0),window=main,anchor='nw')
        self._dashboard_resize_pending=False
        self._dashboard_fit_after_id=None
        self._dashboard_scroll_visible=True
        def fit_dashboard():
            self._dashboard_fit_after_id=None
            self._dashboard_resize_pending=False
            try:
                available=max(1,self.dashboard_canvas.winfo_height())
                required=max(1,main.winfo_reqheight())
                # A large window should grow its results Treeview instead of
                # creating unused bottom canvas space. A small window gets a
                # native scroll region and can still reach every control.
                self.dashboard_canvas.itemconfigure(self.dashboard_window,
                    width=max(1,self.dashboard_canvas.winfo_width()),
                    height=max(required,available))
                self.dashboard_canvas.configure(scrollregion=self.dashboard_canvas.bbox('all'))
                need_scroll=required>available+2
                if need_scroll!=self._dashboard_scroll_visible:
                    self._dashboard_scroll_visible=need_scroll
                    if need_scroll:
                        self.dashboard_scroll.pack(side='right',fill='y',before=self.dashboard_canvas)
                    else:
                        self.dashboard_scroll.pack_forget()
                        self.dashboard_canvas.yview_moveto(0)
            except tk.TclError:
                pass
        def queue_fit(_event=None):
            if not self._dashboard_resize_pending:
                self._dashboard_resize_pending=True
                self._dashboard_fit_after_id=self.root.after_idle(fit_dashboard)
        main.bind('<Configure>',queue_fit)
        self.dashboard_canvas.bind('<Configure>',queue_fit)
        self._fit_dashboard=queue_fit
        def scroll_dashboard(event):
            # Tk's wheel dispatch sometimes happens before a bind_all handler
            # (notably for TButton). Bind both class and all windows while
            # allowing Treeview/Text/Combobox to retain natural scrolling.
            try:
                if event.widget.winfo_toplevel()!=self.root:return
            except (AttributeError,tk.TclError):return
            widget=event.widget
            while widget is not None:
                if isinstance(widget,(ttk.Treeview,tk.Text,ttk.Combobox)):
                    return
                if widget==self.footer_bar or widget==self.root:
                    break
                widget=getattr(widget,'master',None)
            if self._dashboard_scroll_visible:
                delta=getattr(event,'delta',0)
                direction=-1 if delta>0 or getattr(event,'num',0)==4 else 1
                count=max(1,abs(int(delta/120))) if delta else 1
                self.dashboard_canvas.yview_scroll(direction*count*3,'units')
                return 'break'
        self._scroll_dashboard=scroll_dashboard
        self.root.bind_all('<MouseWheel>',scroll_dashboard,add='+')
        self.root.bind_all('<Button-4>',scroll_dashboard,add='+')
        self.root.bind_all('<Button-5>',scroll_dashboard,add='+')
        ttk.Label(main,text='IRAN REMAINS CONNECTED',style='Title.TLabel').pack(anchor='w')
        ttk.Label(main,text='Combine subscriptions → scan the shared pool → explore working nodes → connect with Manual, System Proxy or TUN',
                  style='Muted.TLabel').pack(anchor='w',pady=(0,11))
        self._section_line(main,'GENERAL / SOURCES')
        head=ttk.Frame(main);head.pack(fill='x',pady=(0,7))
        self.url=tk.StringVar(value=self.settings.subscription_url)
        self.binary=tk.StringVar(value=self.settings.singbox_path)
        ttk.Label(head,text='Subscriptions (one per line or comma-separated)').grid(row=0,column=0,sticky='nw')
        self.feed_sources_text=tk.Text(head,height=2,wrap='word',background=PANEL,foreground=TEXT,
                                      insertbackground='white',font=('Segoe UI',9),undo=True)
        self.feed_sources_text.grid(row=0,column=1,columnspan=5,padx=8,sticky='ew')
        self.feed_sources_text.insert('1.0',self.url.get())
        def sync_source(*_):
            current=self.url.get()
            if self.feed_sources_text.get('1.0','end-1c')!=current:
                self.feed_sources_text.delete('1.0','end')
                self.feed_sources_text.insert('1.0',current)
        self.url.trace_add('write',sync_source)
        def source_modified(_event=None):
            if self.feed_sources_text.edit_modified():
                self.feed_sources_text.edit_modified(False)
                self.url.set(self.feed_sources_text.get('1.0','end-1c'))
        self.feed_sources_text.bind('<<Modified>>',source_modified)
        self.feed_sources_text.edit_modified(False)
        ttk.Button(head,text='Browse .txt',command=self.browse_subscription).grid(row=0,column=6,padx=3)
        ttk.Button(head,text='Save settings',command=self.save).grid(row=0,column=7,padx=3)
        ttk.Label(head,text='sing-box core').grid(row=1,column=0,sticky='w',pady=(7,0))
        ttk.Entry(head,textvariable=self.binary).grid(row=1,column=1,columnspan=4,padx=8,pady=(7,0),sticky='ew')
        ttk.Button(head,text='Browse core',command=self.browse_core).grid(row=1,column=5,pady=(7,0))
        ttk.Button(head,text='Test endpoints',command=self.edit_endpoints).grid(row=1,column=6,pady=(7,0),padx=3)
        ttk.Button(head,text='Open output',command=self.open_folder).grid(row=1,column=7,pady=(7,0),padx=3)
        for i in range(1,6):head.columnconfigure(i,weight=1)
        self._section_line(main,'SCAN / MONITOR',top=4)
        config=ttk.Frame(main);config.pack(fill='x',pady=(1,4))
        self.minutes=tk.StringVar(value=str(self.settings.refresh_minutes))
        self.budget=tk.StringVar(value=str(self.settings.budget_mib))
        self.probe_limit=tk.StringVar(value=str(self.settings.probes_per_cycle))
        self.speeds=tk.StringVar(value=str(self.settings.speed_candidates))
        self.shortlist=tk.StringVar(value=str(self.settings.shortlist_size))
        self.latency_cutoff=tk.StringVar(value=str(self.settings.latency_cutoff_ms))
        self.probe_workers=tk.StringVar(value=str(self.settings.probe_workers))
        self.probe_processes=tk.StringVar(value=str(self.settings.probe_processes))
        self.probe_batch=tk.StringVar(value=str(self.settings.probe_batch))
        self.probe_timeout=tk.StringVar(value=str(self.settings.probe_timeout))
        self.speed_workers=tk.StringVar(value=str(self.settings.speed_workers))
        self.speed_seconds=tk.StringVar(value=str(self.settings.speed_seconds))
        self.probe_attempts=tk.StringVar(value=str(self.settings.probe_endpoint_attempts))
        self.confirm_seconds=tk.StringVar(value=str(self.settings.confirm_seconds))
        self.confirm_min_seconds=tk.StringVar(value=str(self.settings.confirm_min_seconds))
        self.exploratory_pct=tk.StringVar(value=str(self.settings.exploratory_speed_pct))
        self.scan_all=tk.BooleanVar(value=self.settings.scan_all)
        self.cached_only=tk.BooleanVar(value=self.settings.use_cached_subscription_for_tests)
        self.source_mode=tk.StringVar(value=self.settings.subscription_proxy_mode)
        self.feed_mode_label=tk.StringVar(value='Feed download: '+self.source_mode.get())
        self.source_mode.trace_add('write',lambda *_:self.feed_mode_label.set('Feed download: '+self.source_mode.get()))
        self.feed_timeout=tk.StringVar(value=str(self.settings.subscription_timeout_seconds))
        self.feed_host=tk.StringVar(value=self.settings.subscription_proxy_host)
        self.feed_port=tk.StringVar(value=str(self.settings.subscription_proxy_port))
        self.feed_username=tk.StringVar(value='')  # per-session, not persisted
        self.feed_password=tk.StringVar(value='')  # per-session, not persisted
        for col,(label,var,width) in enumerate([
            ('Refresh min',self.minutes,9),('Budget MiB',self.budget,9),
            ('Responsive target ms',self.latency_cutoff,13),('Top speed nodes',self.speeds,11),
            ('Latency workers',self.probe_workers,10),('Latency batch',self.probe_batch,10),
            ('Latency timeout s',self.probe_timeout,11)]):
            chunk=ttk.Frame(config);chunk.grid(row=0,column=col,sticky='w',padx=(0,12))
            ttk.Label(chunk,text=label,style='Muted.TLabel').pack(anchor='w')
            ttk.Entry(chunk,textvariable=var,width=width).pack(anchor='w',pady=2)
        # Scan presets and subscription transport are separate, clearly labelled
        # control groups above the detailed advanced tuning fields.
        toolbar=ttk.Frame(main);toolbar.pack(fill='x',pady=(0,3))
        ttk.Label(toolbar,text='Scan presets:',style='Muted.TLabel').pack(side='left',padx=(0,5))
        ttk.Button(toolbar,text='Default scan',command=self.default_preset).pack(side='left',padx=(0,5))
        ttk.Button(toolbar,text='Fast scan',command=self.fast_preset).pack(side='left',padx=(0,25))
        # Mode is SELECTABLE only inside Feed proxy settings. This toolbar
        # reports the saved mode; it has no duplicate dropdown.
        ttk.Label(toolbar,textvariable=self.feed_mode_label,style='Muted.TLabel').pack(side='left',padx=(0,8))
        ttk.Button(toolbar,text='Feed proxy settings',command=self.configure_feed_proxy).pack(side='left')
        # Keep advanced controls available without using table space when
        # users are primarily scanning/connecting. Expansion is reversible.
        self.advanced_expanded=tk.BooleanVar(value=False)
        self.advanced_toggle=ttk.Button(toolbar,text='Advanced scan settings ▸',command=self.toggle_advanced)
        self.advanced_toggle.pack(side='left',padx=(22,0))
        self.advanced_frame=ttk.Frame(main)
        config2=ttk.Frame(self.advanced_frame);config2.pack(fill='x',pady=(3,5))
        for label,var,width in [('Sample limit (if off)',self.probe_limit,9),
                                ('Download workers',self.speed_workers,6),
                                ('Prelim timeout s',self.speed_seconds,6),
                                ('Shortlist',self.shortlist,6),
                                ('Feed timeout s',self.feed_timeout,6),
                                ('Parallel batches',self.probe_processes,6)]:
            sub=ttk.Frame(config2);sub.pack(side='left',padx=(0,15))
            ttk.Label(sub,text=label,style='Muted.TLabel').pack(anchor='w')
            ttk.Entry(sub,textvariable=var,width=width).pack(anchor='w')
        extra=ttk.Frame(self.advanced_frame);extra.pack(fill='x',pady=(0,6))
        for label,var,width in [('Latency URLs/node',self.probe_attempts,5),
                                ('Confirm timeout s',self.confirm_seconds,6),
                                ('Min verified window s',self.confirm_min_seconds,7),
                                ('Slow-ping exploration %',self.exploratory_pct,6)]:
            sub=ttk.Frame(extra);sub.pack(side='left',padx=(0,15))
            ttk.Label(sub,text=label,style='Muted.TLabel').pack(anchor='w')
            ttk.Entry(sub,textvariable=var,width=width).pack(anchor='w')
        # Scan-all remains a visible, frequently used setting even when
        # advanced fields are collapsed.
        scan_all_bar=ttk.Frame(main)
        scan_all_bar.pack(fill='x',pady=(0,4))
        ttk.Checkbutton(scan_all_bar,text='Probe ALL supported nodes',variable=self.scan_all).pack(side='left',padx=(0,20))
        ttk.Checkbutton(scan_all_bar,text='Test saved feed (no download)',variable=self.cached_only).pack(side='left')
        controls=ttk.Frame(main);controls.pack(fill='x',pady=(0,4))
        self.advanced_frame_next=controls
        primary_actions=ttk.Frame(controls);primary_actions.pack(fill='x')
        secondary_actions=primary_actions  # compact single row at normal window widths
        self.monitor_buttons={}
        for label,fun,style in [('Update subscription',self.update_only,None),
                                ('Run one cycle',self.run_once,None),
                                ('Start auto monitoring',self.start,None),
                                ('Run once + auto',self.run_and_monitor,'Accent.TButton'),
                                ('Stop',self.stop,None),
                                ('View logs',self.open_logs,None),
                                ('Copy selected',self.copy_selected,None),
                                ('Save selected',self.save_selected,None),
                                ('Compare selected',self.compare_selected,None)]:
            group=primary_actions if label in ('Update subscription','Run one cycle',
                   'Start auto monitoring','Run once + auto') else secondary_actions
            button=ttk.Button(group,text=label,command=fun,style=style or 'TButton')
            button.pack(side='left',padx=(0,5))
            if label in ('Update subscription','Run one cycle','Start auto monitoring','Run once + auto','Stop'):
                self.monitor_buttons[label]=button
        # Connection controls are intentionally separate from the scanner.
        # No connection starts automatically when the app is launched.
        self._section_line(main,'CONNECT / PROXY',top=2)
        conn=ttk.Frame(main);conn.pack(fill='x',pady=(0,3))
        top=ttk.Frame(conn);top.pack(fill='x',pady=(0,4))
        lower=ttk.Frame(conn);lower.pack(fill='x')
        ttk.Label(top,text='Mode',style='Muted.TLabel').pack(side='left',padx=(0,8))
        self.client_mode=tk.StringVar(value=self.settings.client_mode)
        self.client_mode_selector=ttk.Combobox(top,textvariable=self.client_mode,state='readonly',width=22,
            values=('Manual HTTP/SOCKS5','Windows system proxy','Device-wide TUN'))
        labels={'manual':'Manual HTTP/SOCKS5','system':'Windows system proxy','tun':'Device-wide TUN'}
        self.client_mode.set(labels[self.settings.client_mode])
        self.client_mode_selector.pack(side='left',padx=(0,7))
        self.client_mode_selector.bind('<<ComboboxSelected>>',self._mode_changed)
        ttk.Label(top,text='Local port').pack(side='left',padx=(0,4))
        self.client_port=tk.StringVar(value=str(self.settings.client_listen_port))
        ttk.Entry(top,textvariable=self.client_port,width=7).pack(side='left',padx=(0,7))
        ttk.Button(top,text='Connect highlighted node',command=self.connect_selected).pack(side='left',padx=(0,5))
        ttk.Button(top,text='Disconnect',command=self.disconnect_client).pack(side='left',padx=(0,5))
        ttk.Button(top,text='Test connection',command=self.test_client).pack(side='left',padx=(0,5))
        ttk.Button(top,text='Copy proxy address',command=self.copy_client_proxy).pack(side='left')
        ttk.Label(lower,text='Saved shortlist:',style='Muted.TLabel').pack(side='left',padx=(0,5))
        self.client_shortlist=tk.StringVar(value='best-overall')
        self.client_category_selector=ttk.Combobox(lower,textvariable=self.client_shortlist,state='readonly',width=20,
                     values=('best-overall','best-download-speed','best-ping','best-reliable'))
        self.client_category_selector.pack(side='left',padx=(0,6))
        ttk.Label(lower,text='Rank').pack(side='left',padx=(0,4))
        self.client_rank=tk.StringVar(value='1')
        ttk.Spinbox(lower,textvariable=self.client_rank,from_=1,to=30,width=5).pack(side='left',padx=(0,6))
        ttk.Button(lower,text='Connect shortlist rank',command=self.connect_best).pack(side='left',padx=(0,15))
        self.client_status=tk.StringVar(value='DISCONNECTED · Local proxy does not alter Windows networking')
        ttk.Label(main,textvariable=self.client_status,style='Muted.TLabel',wraplength=1270).pack(anchor='w',pady=(0,3))
        ttk.Label(main,text='Manual mode: only applications using the local proxy take this route; other sites can stay direct. HTTPS content remains encrypted to its website.',
                  style='Muted.TLabel').pack(anchor='w',pady=(0,5))
        self.status=tk.StringVar(value='Ready. Live rows appear as soon as the subscription is parsed.')
        ttk.Label(main,textvariable=self.status,style='Muted.TLabel',wraplength=1220).pack(anchor='w',pady=(0,8))
        self.stats_row=ttk.Frame(main);self.stats_row.pack(fill='x',pady=(0,6))
        self.stat_vars=[]
        for i,label in enumerate(['Total nodes','Supported','Connected','Downloads passed','Stable Mbps','Direct Mbps','Scan HTTP MiB ≥']):
            f=ttk.Frame(self.stats_row,style='Panel.TFrame',padding=7);f.grid(row=0,column=i,padx=(0,8),sticky='ew')
            self.stats_row.columnconfigure(i,weight=1)
            ttk.Label(f,text=label,style='CardSmall.TLabel').pack(anchor='w')
            var=tk.StringVar(value='—');self.stat_vars.append(var)
            ttk.Label(f,textvariable=var,style='Card.TLabel').pack(anchor='w',pady=(5,0))
        sec=ttk.Frame(main);sec.pack(fill='x')
        ttk.Label(sec,text='Scan pool and working nodes',font=('Segoe UI Semibold',12)).pack(side='left')
        ttk.Label(sec,text='Select + Ctrl+C / double-click to copy',style='Muted.TLabel').pack(side='left',padx=14)
        self.timestamp=tk.StringVar(value='')
        ttk.Label(sec,textvariable=self.timestamp,style='Muted.TLabel').pack(side='right')
        self.results_tabs=ttk.Notebook(main)
        self.results_tabs.pack(fill='both',expand=True,pady=(3,4))
        table=ttk.Frame(self.results_tabs)
        working=ttk.Frame(self.results_tabs)
        self.results_tabs.add(table,text='All nodes · combined pool')
        self.results_tabs.add(working,text='Working nodes · HTTPS passed')
        recent=ttk.Frame(self.results_tabs)
        self.results_tabs.add(recent,text='Recent connections')
        def make_table(parent,columns=COLUMNS):
            tree=ttk.Treeview(parent,columns=columns,show='headings',selectmode='extended',height=3)
            for col in columns:
                tree.heading(col,text=COLUMN_LABELS[col],command=lambda c=col,t=tree:self.sort(c,t))
                tree.column(col,width=COLUMN_WIDTHS[col],minwidth=45,anchor='w' if col in ('name','status','encryption') else 'center')
            scroll=ttk.Scrollbar(parent,orient='vertical',command=tree.yview)
            hscroll=ttk.Scrollbar(parent,orient='horizontal',command=tree.xview)
            tree.configure(yscrollcommand=scroll.set,xscrollcommand=hscroll.set)
            tree.grid(row=0,column=0,sticky='nsew')
            scroll.grid(row=0,column=1,sticky='ns')
            hscroll.grid(row=1,column=0,sticky='ew')
            parent.columnconfigure(0,weight=1)
            parent.rowconfigure(0,weight=1)
            tree.bind('<Control-c>',self._copy_hotkey)
            tree.bind('<Double-1>',self._copy_hotkey)
            tree.bind('<Button-3>',self._context_menu)
            return tree
        self.tree=make_table(table)
        self.working_tree=make_table(working)
        recent_actions=ttk.Frame(recent);recent_actions.pack(fill='x',pady=4)
        ttk.Button(recent_actions,text='Reconnect highlighted recent node',command=self.connect_recent).pack(side='left',padx=(0,8))
        ttk.Button(recent_actions,text='Clear recent history',command=self.clear_recent).pack(side='left')
        ttk.Label(recent_actions,text='Reconnect uses the connection mode currently selected above.',style='Muted.TLabel').pack(side='left',padx=15)
        recent_table=ttk.Frame(recent);recent_table.pack(fill='both',expand=True)
        self.recent_tree=make_table(recent_table,RECENT_COLUMNS)
        self.recent_tree.configure(selectmode='browse')
        self.recent_tree.bind('<Double-1>',lambda e:self.connect_recent())
        self.recent_table_sort='connected_at';self.recent_reverse=True
        self.refresh_recent()
        self.context=tk.Menu(self.root,tearoff=0)
        self.context.add_command(label='Copy original URI / outbound',command=self.copy_selected)
        self.context.add_command(label='Explain selected result',command=self.show_reason)
        self.context.add_command(label='Explain encryption / security score',command=self.show_security)
        self.context.add_command(label='Save selected to file',command=self.save_selected)
        self.context.add_separator()
        self.context.add_command(label='Connect this node',command=self.connect_selected)
        self._install_tooltips(main)

    def _install_tooltips(self, main):
        """Hover help for every dashboard setting, metric, button and column."""
        helptext={
            'IRAN REMAINS CONNECTED': 'Scanner plus on-demand sing-box VPN/proxy client. No automatic device connection.',
            'Subscriptions (one per line or comma-separated)': 'Enter multiple HTTP(S) URLs and absolute local paths. Each is fetched separately and duplicate nodes are scanned only once.',
            'Browse .txt': 'Choose a local subscription you already downloaded. The choice is saved immediately.',
            'Save settings': 'Persist these preferences under your Windows user AppData folder. No test is started.',
            'sing-box core': 'Path to the sing-box executable used to route each test. This does not alter Karing or NekoBox.',
            'Browse core': 'Choose your existing sing-box.exe. You can reuse D:\\sing-box.exe.',
            'Test endpoints': 'Edit HTTPS servers used for connectivity checks and download samples. One server alone cannot represent every destination.',
            'Open output': 'Open separately exported Best download speed, Best ping and Best overall profiles and share links.',
            'Refresh min': 'Auto timer: initially waits this many real elapsed minutes. After a cycle ends, it waits this interval again. Sleep/hibernate counts.',
            'Budget MiB': 'Maximum planned HTTP response-body data for download tests in one cycle. Connection overhead is additional.',
            'Responsive target ms': 'HTTPS response-time target for speed-test candidate preference; slow nodes can still be explored.',
            'Top speed nodes': 'Maximum number of latency-passing nodes to try with preliminary downloads. Default 250; not all will be confirmed.',
            'Latency workers': 'Simultaneous HTTPS checks PER sing-box batch. Total potential probes = workers × parallel batches.',
            'Latency batch': 'Number of proxy outbounds loaded into each sing-box testing process. Large values reduce startup overhead but increase memory and ports.',
            'Latency timeout s': 'Wall-clock deadline for one HTTPS response-header check, including CONNECT and TLS. Short deadlines can miss usable slow nodes.',
            'Probe ALL supported nodes': 'Scan every parser-supported node. If unchecked, use the sample limit, rotating through nodes across cycles.',
            'Sample limit (if off)': 'Maximum nodes selected for a cycle when full probing is disabled; history and random exploration rotate candidates.',
            'Download workers': 'Number of simultaneous real HTTPS downloads; too many can make their speeds compete for the same connection.',
            'Prelim timeout s': 'Short per-endpoint download attempt used to find candidates; not a reliable sustained-speed result.',
            'Shortlist': 'Number of nodes exported in each category (if sufficiently many qualify).',
            'Feed timeout s': 'Maximum inactivity during one blocking subscription read. 300s does not mean the entire feed must finish in 300s.',
            'Parallel batches': 'Independent sing-box core processes that test different latency batches simultaneously. More uses more memory/sockets.',
            'Feed proxy settings': 'Only place to select the feed network mode. Save to apply it to subscription updates; benchmark traffic is unaffected.',
            'Test saved feed (no download)': 'Run one cycle reads each selected source’s matching saved snapshot, not the network. Missing cached sources are reported and omitted.',
            'Latency URLs/node': 'How many HTTPS destinations each proxy can try for latency. One is faster; multiple can rescue region-filtered nodes.',
            'Confirm timeout s': 'Observation cap for sustained flow testing; 12 seconds helps expose long pauses and brief bursts. Host-specific result.',
            'Min verified window s': 'A confirmed flow needs this long, at least 75% meaningful active seconds and low-percentile throughput without prolonged gaps.',
            'Slow-ping exploration %': 'Share of speed candidates reserved for slower HTTPS responders, which can still offer high throughput.',
            'Fast scan': 'Aggressive: 4 isolated sing-box processes and 128 parallel nodes per batch. Faster but more network and memory pressure.',
            'Default scan': 'Balanced: 2 sing-box processes, 64-node batches, 3-second latency limit and up to 250 speed candidates. Does not start a test.',
            'Start auto monitoring': 'ARM the scheduler; first full cycle is due after Refresh min. Does NOT start one immediately. Runs only while this app stays open.',
            'Run once + auto': 'Run a full cycle NOW and then repeat Refresh min after each finished cycle. No need to run an initial test separately.',
            'Stop': 'Request cancellation of the current operation. Existing exports and last successful results are preserved.',
            'Run one cycle': 'Combine feeds, test HTTPS latency, verify sustained downloads and export shortlists. Only responding nodes enter the Working nodes tab.',
            'Update subscription': 'Download (or read local file) and parse nodes; do not run proxy speed tests.',
            'View logs': 'Open privacy-filtered diagnostic events. Review log content before sharing it.',
            'Copy selected': 'Copy the exact original URI when present; otherwise copy sing-box outbound JSON. Treat it as a credential.',
            'Save selected': 'Write selected original share links or JSON to a file chosen by you.',
            'Compare selected': 'Retest ONE selected proxy against two distinct HTTPS download hosts using the same sing-box engine. Uses up to 8 MiB; does not change rankings.',
            'Mode': 'Changing this selector while connected safely reconnects the SAME node using the new mode. TUN requires administrator rights.',
            'Local port': 'Loopback-only mixed HTTP/SOCKS5 listener; default 20808. Never exposed to other network devices.',
            'Connect highlighted node': 'Connect the single highlighted supported node in All nodes or Working nodes; does not use shortlist rankings.',
            'Connect shortlist rank': 'Connect a numbered node from a saved Best overall / Best download / Best ping / Best reliable shortlist. It does not require highlighting a table row.',
            'Rank': '1 = best ranked saved node; higher ranks use that exact shortlisted proxy outbound.',
            'Test connection': 'Make a genuine HTTPS request through the connected local proxy; local listener readiness alone does not prove the node works.',
            'Disconnect': 'Stop the client and restore Windows system proxy settings if the app still owns them.',
            'Copy proxy address': 'Copy http://127.0.0.1:PORT for browser/OS manual proxy use. SOCKS5 runs on the same port.',
            'Total nodes': 'Total unique parsed subscription entries, including unsupported ones.',
            'Supported': 'Nodes whose options the parser could translate into a sing-box outbound. They are not necessarily reachable.',
            'Connected': 'Nodes that returned an acceptable HTTPS response through their own proxy during this cycle.',
            'Downloads passed': 'Successful preliminary download attempts / total attempted. This does not imply sustained speeds.',
            'Stable Mbps': 'Highest verified lower-quartile two-second download rate, including idle periods; test-host-specific Mbps, not a guarantee of Karing speed.',
            'Scan HTTP MiB ≥': 'Live measured bytes from feeds, latency CONNECT/HTTPS headers, download tests and baseline. Lower bound: excludes TLS handshakes, transport/encryption overhead and unobserved failed transfers.',
            'Direct Mbps': 'Speed to a test destination without a proxy. A proxy can appear faster because it uses a different route/server.',
            'Scan pool and working nodes': 'All nodes combines subscriptions; Working nodes lists HTTPS-successful proxies from the current scan.',
            'Select + Ctrl+C / double-click to copy': 'Be careful: share URIs frequently contain proxy credentials. Do not post them publicly.',
            'Ready. Live rows appear as soon as the subscription is parsed.': 'Operation status, test phase and errors appear here.',
            'No cycle has been run yet.': 'Current operation details and exports appear here.',
        }
        fields={
            str(self.url): helptext['Subscriptions (one per line or comma-separated)'],
            str(self.client_port): helptext['Local port'],
            str(self.binary): helptext['sing-box core'],
            str(self.minutes): helptext['Refresh min'],
            str(self.budget): helptext['Budget MiB'],
            str(self.latency_cutoff): helptext['Responsive target ms'],
            str(self.speeds): helptext['Top speed nodes'],
            str(self.probe_workers): helptext['Latency workers'],
            str(self.probe_batch): helptext['Latency batch'],
            str(self.probe_timeout): helptext['Latency timeout s'],
            str(self.probe_limit): helptext['Sample limit (if off)'],
            str(self.speed_workers): helptext['Download workers'],
            str(self.speed_seconds): helptext['Prelim timeout s'],
            str(self.shortlist): helptext['Shortlist'],
            str(self.feed_timeout): helptext['Feed timeout s'],
            str(self.probe_processes): helptext['Parallel batches'],
            str(self.probe_attempts): helptext['Latency URLs/node'],
            str(self.confirm_seconds): helptext['Confirm timeout s'],
            str(self.confirm_min_seconds): helptext['Min verified window s'],
            str(self.exploratory_pct): helptext['Slow-ping exploration %'],
        }
        def walk(widget):
            for child in widget.winfo_children():
                text=''
                if isinstance(child,(ttk.Label,ttk.Button,ttk.Checkbutton)):
                    try:text=helptext.get(child.cget('text'),'')
                    except tk.TclError:pass
                if child is getattr(self,'feed_sources_text',None):
                    text=helptext['Subscriptions (one per line or comma-separated)']
                if isinstance(child,(ttk.Entry,ttk.Combobox)):
                    try:text=fields.get(str(child.cget('textvariable')),'')
                    except tk.TclError:pass
                if isinstance(child,ttk.Label) and not text:
                    try:
                        v=child.cget('textvariable')
                        if v==str(self.status):text='Shows progress and the current stage; errors are also logged.'
                        if v==str(self.footer):text='Subscription details, export categories and log status.'
                    except tk.TclError:pass
                if text:self.tip.attach(child,text)
                walk(child)
        walk(main)
        self.tip.attach(self.client_mode_selector, 'Changing mode while connected first checks compatibility, then disconnects and reconnects the same node. Manual = selected apps only; System = OS proxy-aware apps; TUN = device-wide, needs administrator rights.')
        self.tip.attach(self.client_category_selector, 'Saved shortlists. Best reliable requires confirmed conservative Flow ≥1.000 Mbps and ranks by historical HTTPS success.')
        for tab_tree in (self.tree,self.working_tree):
            self.tip.tree_headings(tab_tree,[
            'Current display order after sorting; not a global node quality rank.',
            'Node name from source subscription. Select and Ctrl+C to copy original configuration.',
            'Protocol family such as VLESS, VMess, Shadowsocks or HTTP.',
            'Configured proxy-hop encryption. HTTPS site encryption is a separate layer. Unassessed means unknown, not necessarily cleartext.',
            'Heuristic 0–100 based on proxy configuration ONLY; not independently tested, not anonymity, trust, DNS safety, or a privacy guarantee.',
            'HTTPS response-header latency via this proxy, including connection and TLS. Not ICMP ping.',
            'Mean HTTPS download speed (Mbps), still susceptible to bursts; compare Flow Mbps.',
            'Lower-quartile two-second Mbps including zero-traffic periods. Used for verified download rankings.',
            'Elapsed measurement window in seconds, including setup and waiting.',
            'Historical connection success estimate across recent cycles; early values may be uncertain.',
            'Yes requires long observation, few idle intervals and meaningful throughput in slow periods. Still test-host-specific.',
            'Latest phase, rejection reason or sample qualification. Right-click a row for detailed diagnostics.',
        ])
        self.tip.tree_headings(self.recent_tree,[
            'When the app successfully established the connection; not a scan timestamp.',
            'Mode used at that time. Reconnect uses the mode currently selected above.',
            'Rank from the source table when recorded; a dash means no scan measurement was available.',
            'Name of the previously connected proxy; full original outbound retained privately.',
            'Protocol family of the previously connected proxy.',
            'Configured upstream encryption, recomputed from this saved outbound.',
            'Configuration-only security heuristic. No provider or DNS privacy guarantee.',
            'HTTPS latency when this connection was stored, otherwise unknown.',
            'Average speed when measured, otherwise unknown.',
            'Conservative verified flow when measured, otherwise unknown.',
            'Observation window, if available at connection time.',
            'Historical HTTPS reliability from the scan, not continuous uptime.',
            'Stable-flow verification at connection time, if previously tested.',
            'Last observed scan status at the time of connection.',
        ])

    def save(self):
        try:
            s=self.settings;s.subscription_url=self.url.get().strip();s.singbox_path=self.binary.get().strip()
            s.refresh_minutes=int(self.minutes.get());s.budget_mib=float(self.budget.get())
            s.probes_per_cycle=int(self.probe_limit.get());s.speed_candidates=int(self.speeds.get())
            s.shortlist_size=int(self.shortlist.get());s.latency_cutoff_ms=int(self.latency_cutoff.get())
            s.probe_workers=int(self.probe_workers.get());s.probe_batch=int(self.probe_batch.get())
            s.probe_processes=int(self.probe_processes.get())
            s.probe_timeout=float(self.probe_timeout.get());s.speed_workers=int(self.speed_workers.get())
            s.speed_seconds=float(self.speed_seconds.get());s.scan_all=bool(self.scan_all.get())
            s.use_cached_subscription_for_tests=bool(self.cached_only.get())
            s.probe_endpoint_attempts=int(self.probe_attempts.get())
            s.confirm_seconds=float(self.confirm_seconds.get())
            s.confirm_min_seconds=float(self.confirm_min_seconds.get())
            s.exploratory_speed_pct=int(self.exploratory_pct.get())
            s.subscription_proxy_mode=self.source_mode.get()
            s.subscription_proxy_host=self.feed_host.get().strip()
            s.subscription_proxy_port=int(self.feed_port.get())
            s.subscription_proxy_username=self.feed_username.get()
            s.subscription_proxy_password=self.feed_password.get()
            s.subscription_timeout_seconds=int(self.feed_timeout.get())
            s.client_mode=self._client_mode_key()
            s.client_listen_port=int(self.client_port.get())
            s.save();self.status.set('Settings saved locally to '+str(DATA_DIR));return True
        except (ValueError,OSError) as exc:
            messagebox.showerror('Invalid settings',str(exc));return False

    def configure_feed_proxy(self):
        """Diagnose subscription-only proxy without changing the benchmark route."""
        from urllib.request import Request
        from .feed_proxy import validate_proxy_settings, build_feed_opener
        from .diagnostics import error_kind

        # Transactional dialog: Cancel/Escape never changes the active mode.
        form_mode=tk.StringVar(value=self.source_mode.get())
        form_host=tk.StringVar(value=self.feed_host.get())
        form_port=tk.StringVar(value=self.feed_port.get())
        form_user=tk.StringVar(value=self.feed_username.get())
        form_password=tk.StringVar(value=self.feed_password.get())
        dialog=tk.Toplevel(self.root)
        dialog.title('Subscription download proxy')
        dialog.transient(self.root)
        dialog.grab_set()
        dialog.configure(bg=BG)
        dialog.resizable(False,False)
        panel=ttk.Frame(dialog,padding=18);panel.pack(fill='both',expand=True)
        ttk.Label(panel,text='Subscription fetching only — never applies to proxy benchmarks.').grid(
            row=0,column=0,columnspan=2,sticky='w',pady=(0,12))
        ttk.Label(panel,text='Active mode').grid(row=1,column=0,sticky='w',pady=5)
        ttk.Combobox(panel,textvariable=form_mode,
                     values=('system','direct','manual-http','manual-socks5'),
                     width=34,state='readonly').grid(row=1,column=1,sticky='ew',padx=(12,0))
        for i,(title,var,secret) in enumerate([
            ('Proxy host / IP',form_host,False),('Port',form_port,False),
            ('Username (optional)',form_user,False),
            ('Password (not saved)',form_password,True)]):
            ttk.Label(panel,text=title).grid(row=i+2,column=0,sticky='w',pady=5)
            ttk.Entry(panel,textvariable=var,width=37,show='*' if secret else '').grid(
                row=i+2,column=1,sticky='ew',padx=(12,0),pady=5)
        note=('For Karing, select manual-socks5 and the SOCKS5 listener port '
              '(or manual-http and its HTTP proxy port). The displayed IP/port '
              'are IGNORED in system/direct mode. TUN should not be required. '
              'Proxy authentication stays in memory only.')
        ttk.Label(panel,text=note,style='Muted.TLabel',wraplength=470).grid(
            row=6,column=0,columnspan=2,sticky='w',pady=(12,8))
        route_status=tk.StringVar(value='Test the selected feed path before downloading a large list.')
        ttk.Label(panel,textvariable=route_status,style='Muted.TLabel',wraplength=460).grid(
            row=7,column=0,columnspan=2,sticky='w',pady=(0,8))
        probe_queue=queue.Queue()

        def test_route():
            try:
                mode=form_mode.get()
                host=form_host.get().strip()
                port=int(form_port.get())
                user=form_user.get();password=form_password.get()
                validate_proxy_settings(mode,host,port,user,password)
                remote=[x for x in split_subscription_sources(self.url.get())
                        if x.startswith(('https://','http://'))]
                if not remote:
                    raise ValueError('Add a remote HTTP(S) subscription URL to test.')
                source=remote[0]
            except ValueError as exc:
                route_status.set(str(exc));return
            route_status.set(f'Testing {mode} route to the selected subscription…')
            probe_button.configure(state='disabled')
            def worker():
                try:
                    opener=build_feed_opener(mode,host,port,user,password)
                    request=Request(source,headers={'Range':'bytes=0-0',
                                                  'User-Agent':'IranProxyMonitor/1.0.14'})
                    with opener.open(request,timeout=12) as response:
                        response.read(1)  # do not download a multi-megabyte feed
                        code=response.status
                    event('feed-route-test',proxy_mode=mode,success=True)
                    probe_queue.put(f'Route works (HTTP {code}). You can update this subscription.')
                except Exception as exc:
                    kind=error_kind(exc)
                    failure=record_failure(exc,'feed-route-test',warning=True)
                    probe_queue.put(f'Quick route check failed ({kind}, incident {failure.incident_id}). '
                                    'A slow feed can still work with the longer Update subscription timeout.')
            threading.Thread(target=worker,daemon=True,name='feed-route-test').start()

        pending_poll=[None]
        def close_dialog():
            if pending_poll[0] is not None:
                try:dialog.after_cancel(pending_poll[0])
                except tk.TclError:pass
                pending_poll[0]=None
            dialog.destroy()

        def check_test():
            try:
                result=probe_queue.get_nowait()
            except queue.Empty:
                pass
            else:
                route_status.set(result)
                probe_button.configure(state='normal')
            if dialog.winfo_exists():pending_poll[0]=dialog.after(120,check_test)

        def accept():
            try:
                mode=form_mode.get()
                host=form_host.get().strip()
                port=int(form_port.get())
                user=form_user.get();password=form_password.get()
                validate_proxy_settings(mode,host,port,user,password)
            except ValueError as exc:
                messagebox.showerror('Proxy settings',str(exc),parent=dialog)
                return
            previous=(self.source_mode.get(),self.feed_host.get(),self.feed_port.get(),
                      self.feed_username.get(),self.feed_password.get())
            self.source_mode.set(mode);self.feed_host.set(host);self.feed_port.set(str(port))
            self.feed_username.set(user);self.feed_password.set(password)
            if self.save():
                close_dialog()
            else:
                for var,value in zip((self.source_mode,self.feed_host,self.feed_port,
                                      self.feed_username,self.feed_password),previous):
                    var.set(value)

        probe_button=ttk.Button(panel,text='Test feed route',command=test_route)
        probe_button.grid(row=8,column=0,sticky='w')
        ttk.Button(panel,text='Save proxy settings',command=accept).grid(row=8,column=1,sticky='e')
        ttk.Button(panel,text='Cancel',command=close_dialog).grid(row=9,column=0,sticky='w',pady=(9,0))
        dialog.protocol('WM_DELETE_WINDOW',close_dialog)
        dialog.bind('<Escape>',lambda _event: close_dialog())
        pending_poll[0]=dialog.after(120,check_test)
        dialog.wait_window()

    def default_preset(self):
        # Balanced configuration for general-purpose scans; no automatic run.
        for var,value in ((self.probe_workers,'64'),(self.probe_batch,'64'),
                          (self.probe_processes,'2'),(self.probe_timeout,'3.0'),
                          (self.probe_attempts,'2'),(self.speed_workers,'4'),
                          (self.speed_seconds,'4'),(self.confirm_seconds,'12'),
                          (self.confirm_min_seconds,'8'),(self.exploratory_pct,'30'),
                          (self.budget,'256'),(self.speeds,'250')):
            var.set(value)
        self.status.set('Default balanced scan selected. Run a cycle or Save settings to keep it.')

    def fast_preset(self):
        # Explicit action: never silently override someone's saved preferences.
        for var,value in ((self.probe_workers,'128'),(self.probe_batch,'128'),
                          (self.probe_processes,'4'),
                          (self.probe_timeout,'2.5'),(self.probe_attempts,'1'),
                          (self.speed_workers,'5'),(self.speed_seconds,'3.5'),
                          (self.confirm_seconds,'12'),(self.confirm_min_seconds,'8'),
                          (self.exploratory_pct,'30'),(self.budget,'256'),(self.speeds,'250')):
            var.set(value)
        self.status.set('Aggressive preset applied: 4 × 128 HTTPS probes, 250 speed candidates; run a cycle to save.')

    def browse_subscription(self):
        path=filedialog.askopenfilename(title='Select a proxy subscription',
               filetypes=[('Subscriptions','*.txt *.yaml *.yml *.json'),('All files','*.*')])
        if path:
            current=split_subscription_sources(self.url.get())
            if path not in current:
                current.append(path)
            self.url.set('\n'.join(current))
            self.save()  # Explicit browsing immediately persists the new source.
            if self.running:
                self.status.set(f'Local file saved ({os.path.getsize(path):,} bytes). Current cycle still uses its prior source; click Stop and wait before Update subscription.')
            else:
                self.status.set(f'Local subscription added ({os.path.getsize(path):,} bytes). Update subscription to merge the pool.')

    def browse_core(self):
        path=filedialog.askopenfilename(title='Select sing-box executable',filetypes=[('EXE','*.exe'),('All','*.*')])
        if path:self.binary.set(path)

    def edit_endpoints(self):
        d=tk.Toplevel(self.root);d.title('HTTPS test endpoints');d.geometry('760x540')
        d.configure(bg=BG);d.transient(self.root)
        label_a=ttk.Label(d,text='Connectivity URLs (one HTTPS URL per line)')
        label_a.pack(anchor='w',padx=15,pady=(10,3))
        a=tk.Text(d,height=8,background=PANEL,foreground=TEXT,insertbackground='white')
        a.pack(fill='both',expand=True,padx=15);a.insert('1.0','\n'.join(self.settings.connectivity_urls))
        self.tip.attach(label_a,'HTTPS response-header probes. Multiple URLs help when one destination is filtered.')
        self.tip.attach(a,'One HTTPS address per line. In fast mode each node tries only the first rotated URL, not all URLs.')
        label_b=ttk.Label(d,text='Download URL templates (optional {bytes} placeholder)')
        label_b.pack(anchor='w',padx=15,pady=(10,3))
        b=tk.Text(d,height=7,background=PANEL,foreground=TEXT,insertbackground='white')
        b.pack(fill='both',expand=True,padx=15);b.insert('1.0','\n'.join(self.settings.download_urls))
        self.tip.attach(label_b,'HTTPS download sources. Compare selected needs at least two distinct hosts.')
        self.tip.attach(b,'Use {bytes} in an HTTPS URL if the server supports selecting a response size. Results from one host are not general VPN speeds.')
        def commit():
            x=[x.strip() for x in a.get('1.0','end').splitlines() if x.strip()]
            y=[x.strip() for x in b.get('1.0','end').splitlines() if x.strip()]
            if not x or not y or any(not z.startswith('https://') for z in x+y):
                messagebox.showerror('Invalid URLs','Enter HTTPS endpoints for both types.',parent=d);return
            self.settings.connectivity_urls=x;self.settings.download_urls=y
            if self.save():d.destroy()
        save_button=ttk.Button(d,text='Save endpoints',command=commit,style='Accent.TButton')
        save_button.pack(pady=12)
        self.tip.attach(save_button,'Save your HTTPS test endpoint list for later monitoring and selected-node comparisons.')

    def open_logs(self):
        LOG_DIR.mkdir(parents=True,exist_ok=True);LOG_FILE.touch(exist_ok=True)
        if os.name=='nt':os.startfile(LOG_FILE)
        else:
            try:subprocess.Popen(['xdg-open',str(LOG_FILE)],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
            except OSError:messagebox.showinfo('Diagnostic log',str(LOG_FILE))

    def open_folder(self):
        OUT.mkdir(exist_ok=True)
        if os.name=='nt':os.startfile(OUT)
        else:
            try:subprocess.Popen(['xdg-open',str(OUT)],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
            except OSError:messagebox.showinfo('Output folder',str(OUT))

    def _copy_hotkey(self,event=None):
        self.copy_selected();return 'break'

    def _active_tree(self):
        index=self.results_tabs.index('current')
        return self.working_tree if index == 1 else self.recent_tree if index == 2 else self.tree

    def _context_menu(self,event):
        tree=event.widget if isinstance(event.widget,ttk.Treeview) else self._active_tree()
        iid=tree.identify_row(event.y)
        if iid and iid not in tree.selection():tree.selection_set(iid)
        self.context.tk_popup(event.x_root,event.y_root)
        self.context.grab_release()

    def selected_nodes(self):
        return [self.nodes_by_id[i] for i in self._active_tree().selection() if i in self.nodes_by_id]

    def show_reason(self):
        chosen=self.selected_nodes()
        if not chosen:
            self.footer.set('Select a node to see why it was classified as unsupported.')
            return
        lines=[]
        for node in chosen[:25]:
            state=self.row_state.get(node.id,{})
            if node.problems:
                reason='; '.join(node.problems)
            elif state.get('core_error'):
                reason=state['core_error']
            elif not node.outbound:
                reason='No supported outbound could be produced'
            else:
                reason='Parser supported this node. '+str(state.get('status','Untested'))
            # A parser issue string could include user-controlled option values;
            # display locally but do not persist to the diagnostic log.
            lines.append(node.name+' ['+node.protocol+']: '+reason)
        if len(chosen)>25:lines.append(f'... and {len(chosen)-25} more selected nodes')
        messagebox.showinfo('Node compatibility / test status','\n\n'.join(lines),parent=self.root)

    def show_security(self):
        tree=self._active_tree()
        entries=[]
        if tree is self.recent_tree:
            for iid in tree.selection():
                try:
                    row=self.recent_entries[int(iid)]
                    entries.append((row['name'],row['outbound']))
                except (ValueError,IndexError,KeyError):pass
        else:
            entries=[(n.name,n.outbound) for n in self.selected_nodes()]
        if not entries:
            self.footer.set('Highlight a node to inspect its configured encryption.');return
        text=[]
        for name,outbound in entries[:15]:
            sec=assess_outbound(outbound)
            value='unassessed' if sec.score is None else f'{sec.score}/100'
            text.append(f'{name}: {sec.encryption} | Config security {value}\n{sec.explanation}')
        text.append('Scores describe configuration ONLY, not tested cryptographic security, provider trust, DNS leaks, or anonymity. HTTPS sites have their own encryption.')
        messagebox.showinfo('Proxy-hop encryption / configuration security','\n\n'.join(text),parent=self.root)

    def copy_selected(self):
        items=self.selected_nodes()
        if not items:
            self.footer.set('Select any loaded row first; original links are available even before testing.')
            return
        payload='\n'.join(copyable_config(n) for n in items)
        self.root.clipboard_clear();self.root.clipboard_append(payload);self.root.update_idletasks()
        kinds=sum(n.source_kind=='link' for n in items)
        self.footer.set(f'Copied {len(items)} configuration(s) to clipboard ({kinds} original share links; '
                        f'{len(items)-kinds} JSON/other entries). Treat as credentials; do not share publicly.')

    def save_selected(self):
        nodes=self.selected_nodes()
        if not nodes:
            self.footer.set('Select one or more rows first.');return
        if len(nodes)>1 and any(n.source_kind!='link' for n in nodes):
            messagebox.showwarning('Mixed formats','Multi-selection export requires share links. '
                                   'Copy non-link entries individually as sing-box outbound JSON.');return
        ext='.txt' if all(n.source_kind=='link' for n in nodes) else '.json'
        filename=filedialog.asksaveasfilename(title='Export selected configurations',defaultextension=ext,
                   initialfile='selected-nodes'+ext,filetypes=[('Share links','*.txt'),('JSON','*.json'),('All','*.*')])
        if not filename:return
        payload='\n'.join(copyable_config(n) for n in nodes)+'\n'
        try:
            with open(filename,'w',encoding='utf-8') as fh:fh.write(payload)
            self.footer.set(f'Saved {len(nodes)} selected configuration(s) to your chosen file.')
        except OSError as exc:messagebox.showerror('Could not save',str(exc))

    def _client_mode_key(self):
        mapping={'Manual HTTP/SOCKS5':'manual','Windows system proxy':'system',
                 'Device-wide TUN':'tun'}
        return mapping.get(self.client_mode.get(), self.client_mode.get())

    def _sync_mode_to_live_connection(self):
        if not self.connection.active:return
        labels={'manual':'Manual HTTP/SOCKS5','system':'Windows system proxy','tun':'Device-wide TUN'}
        self.client_mode.set(labels.get(self.connection.mode,'Manual HTTP/SOCKS5'))
        # A failed switch must not persist a TUN/system setting that was never
        # activated. Preserve existing settings except for the connection mode.
        if self.settings.client_mode != self.connection.mode:
            self.settings.client_mode=self.connection.mode
            try:self.settings.save()
            except (OSError,ValueError):pass

    def _mode_changed(self,_event=None):
        """Changing a connected mode reconnects the SAME node, never selects another."""
        requested=self._client_mode_key()
        if self.client_busy or self.connection.connecting:
            self._deferred_mode=requested
            self.client_status.set('Mode change queued; applies after the current connection operation.')
            return
        if not self.connection.active or requested==self.connection.mode:
            return
        if self.running or self.comparing:
            self.client_status.set('Finish the scan before switching the connected client mode.')
            self._sync_mode_to_live_connection();return
        if requested=='tun' and (sys.platform!='win32' or not is_administrator()):
            self.client_status.set('TUN requires Windows administrator rights; current connection retained.')
            self._sync_mode_to_live_connection();return
        if self._active_connection is None:
            self.client_status.set('Current node not recorded; reconnect it manually to change mode.')
            self._sync_mode_to_live_connection();return
        try:
            if not self.save():
                self._sync_mode_to_live_connection();return
            port=int(self.connection.port)
        except (ValueError,TypeError):
            self._sync_mode_to_live_connection();return
        outbound,name,metrics=self._active_connection
        outbound=copy.deepcopy(outbound)
        old_mode=self.connection.mode
        self.client_busy=True
        self._pending_connection=(copy.deepcopy(outbound),name,requested,dict(metrics))
        self.client_status.set(f'Switching {old_mode} → {requested}: checking, then reconnecting the same node…')
        def work():
            switched_off=False
            try:
                # Check the new mode BEFORE stopping the working connection.
                if not check_core(find_singbox(binary),client_config(outbound,requested,port)):
                    raise RuntimeError('sing-box rejected the requested mode; old connection retained.')
                self.connection.stop();switched_off=True
                if self.client_disconnect_after_busy:
                    self.queue.put(('client_disconnected','Switch cancelled by user.'))
                    return
                result=self.connection.start(binary,outbound,name,requested,port,
                    progress=lambda m:self.queue.put(('client_progress',m)))
                self.queue.put(('client_connected',result))
            except Exception as exc:
                # Roll back to the original working connection if a new mode fails
                # AFTER disconnect. Never silently fall back to a direct route.
                if switched_off and not self.client_disconnect_after_busy:
                    try:
                        self.connection.start(binary,outbound,name,old_mode,port)
                        self.queue.put(('client_rollback',
                            f'Switch to {requested} failed ({type(exc).__name__}); restored {old_mode} connection.'))
                        return
                    except Exception:
                        pass
                self.queue.put(('client_error',f'Mode switch to {requested}: {type(exc).__name__}; '
                                                  'verify connection before browsing.'))
            finally:
                self.queue.put(('client_ready',None))
        # Do not read the mode/port from user-editable fields in the worker.
        binary=self.binary.get().strip()
        self.client_thread=threading.Thread(target=work,daemon=False)
        self.client_thread.start()

    def connect_selected(self):
        chosen=self.selected_nodes()
        if len(chosen)!=1 or not chosen[0].supported:
            messagebox.showinfo('Connect selected','Select exactly one parser-supported node in the table.',parent=self.root)
            return
        self._connect_outbound(chosen[0].outbound,chosen[0].name)

    def connect_best(self):
        try:
            name,outbound=saved_shortlist_node(self.client_shortlist.get(),rank=int(self.client_rank.get()))
        except (OSError,ValueError,TypeError) as exc:
            messagebox.showerror('Saved shortlist',str(exc),parent=self.root)
            return
        self._connect_outbound(outbound,name)

    def _recent_metrics(self,outbound):
        # Record observations only if this exact outbound is in the current scan;
        # absent measurements are shown as unknown, never invented.
        key=Node('match',str(outbound.get('type','unknown')),outbound,'history').id
        r=self.row_state.get(key,{})
        return {field:r[field] for field in ('latency','mbps','flow_mbps','seconds','reliability','confirmed','status','rank') if field in r}

    def refresh_recent(self):
        if not hasattr(self,'recent_tree'):return
        self.recent_entries=recent_connections()
        self.recent_tree.delete(*self.recent_tree.get_children())
        for i,row in enumerate(self.recent_entries):
            stamp=datetime.fromtimestamp(row.get('connected_at',0)).strftime('%Y-%m-%d %H:%M')
            r=row.get('metrics') if isinstance(row.get('metrics'),dict) else {}
            sec=assess_outbound(row['outbound'])
            num=lambda key,places: '—' if r.get(key) is None else f'{r[key]:.{places}f}'
            rate=r.get('mbps')
            values=(stamp,row.get('mode','manual'),r.get('rank','—'),row['name'],
                    row['outbound'].get('type','—'),sec.encryption,
                    '—' if sec.score is None else sec.score,num('latency',1),
                    num('mbps',3),num('flow_mbps',3),num('seconds',1),
                    '—' if r.get('reliability') is None else f'{r["reliability"]*100:.0f}%',
                    '—' if rate is None else ('Yes' if r.get('confirmed') else 'No'),
                    r.get('status','Historical connection; not scanned'))
            self.recent_tree.insert('','end',iid=str(i),values=values)
        self.results_tabs.tab(2,text=f'Recent connections ({len(self.recent_entries)})')

    def connect_recent(self):
        selection=self.recent_tree.selection()
        if not selection:
            self.client_status.set('Highlight one recent connection first.')
            return
        row=self.recent_entries[int(selection[0])]
        self._connect_outbound(row['outbound'],row['name'],metrics=row.get('metrics'))

    def clear_recent(self):
        if messagebox.askyesno('Clear recent connections',
                               'Delete the ten-entry local connection history?',parent=self.root):
            clear_connections()
            self.refresh_recent()

    def _connect_outbound(self,outbound,name,metrics=None):
        if self.client_busy or self.connection.connecting or self.connection.active:
            self.client_status.set('Already connected or changing state. Disconnect first.')
            return
        if self.running or self.comparing:
            self.client_status.set('Wait for the scanner/comparison to finish before connecting, to keep benchmarks independent.')
            return
        warnings = connection_warnings(outbound)
        if warnings and not messagebox.askyesno('Proxy security warning',
                '\n\n'.join(warnings)+'\n\nConnect anyway?',parent=self.root):
            self.client_status.set('Connection canceled: node security warning.')
            return
        if not self.save():return
        self.client_busy=True
        mode=self._client_mode_key();port=int(self.client_port.get())
        self._pending_connection=(copy.deepcopy(outbound),str(name),mode,metrics if metrics is not None else self._recent_metrics(outbound))
        binary=self.binary.get().strip()
        self.client_status.set('Connecting… checking configuration and starting a separate sing-box core.')
        def work():
            try:
                result=self.connection.start(binary,outbound,name,mode,port,
                    progress=lambda m:self.queue.put(('client_progress',m)))
                self.queue.put(('client_connected',result))
            except Exception as exc:
                # Network/config errors can contain credentials; never log raw
                # exceptions. Fixed category + the safe user-facing reason.
                msg=str(exc)
                if not isinstance(exc,(RuntimeError,PermissionError,ValueError,TimeoutError,OSError)):
                    msg=type(exc).__name__
                self.queue.put(('client_error',msg))
            finally:self.queue.put(('client_ready',None))
        self.client_thread=threading.Thread(target=work,daemon=False)
        self.client_thread.start()

    def disconnect_client(self):
        if self.client_busy:
            self.client_disconnect_after_busy = True
            self.connection._stop_requested.set()
            self.client_status.set('Disconnect requested; waiting for startup/stop to finish.')
            return
        if not self.connection.active:
            self.client_status.set('Already disconnected.')
            return
        self.client_busy=True
        self.client_status.set('Disconnecting and restoring system settings…')
        def work():
            try:self.queue.put(('client_disconnected',self.connection.stop()))
            except Exception as exc:self.queue.put(('client_error','Disconnect error: '+type(exc).__name__))
            finally:self.queue.put(('client_ready',None))
        self.client_thread=threading.Thread(target=work,daemon=False)
        self.client_thread.start()

    def test_client(self):
        if self.client_busy or not self.connection.active:
            self.client_status.set('Connect a proxy node first, then test its HTTPS traffic.')
            return
        port=self.connection.port
        endpoint=self.settings.connectivity_urls[0]
        self.client_busy=True
        self.client_status.set('Testing real HTTPS traffic through the selected node…')
        def work():
            from .engine import strict_https_probe
            try:
                _,_,ms=strict_https_probe(endpoint,port,8.0,self.connection._stop_requested)
                self.queue.put(('client_verified',f'HTTPS verified through connected proxy: {ms:.0f} ms to test host.'))
            except Exception as exc:
                self.queue.put(('client_verified','HTTPS check FAILED ('+type(exc).__name__+
                                '). Local listener exists, but this host was not reachable.'))
            finally:self.queue.put(('client_ready',None))
        self.client_thread=threading.Thread(target=work,daemon=False)
        self.client_thread.start()

    def copy_client_proxy(self):
        port=self.connection.port if self.connection.active else self.client_port.get()
        try:
            p=int(port)
            if not 1024<=p<=65535:raise ValueError()
        except (TypeError,ValueError):
            self.client_status.set('Set a valid local port first.');return
        address=f'http://127.0.0.1:{p}'
        self.root.clipboard_clear();self.root.clipboard_append(address);self.root.update_idletasks()
        self.client_status.set(f'Copied {address}. SOCKS5 is also available at 127.0.0.1:{p}.')

    def compare_selected(self):
        if self.running or self.comparing:
            self.status.set('A test is already running. Wait until it completes before comparing a node.')
            return
        selected=self.selected_nodes()
        if len(selected)!=1:
            messagebox.showinfo('Compare selected', 'Select exactly one supported node.', parent=self.root)
            return
        if not selected[0].supported:
            messagebox.showwarning('Unsupported node', 'This node cannot be tested by the current parser.',parent=self.root)
            return
        if not self.save():return
        self.cancel.clear();self.comparing=True
        snapshot=copy.deepcopy(self.settings)
        node=selected[0]
        self.status.set('Testing selected node against two distinct HTTPS servers; may consume up to 8 MiB.')
        def worker():
            try:
                result=compare_node(node,snapshot,self.cancel,
                                    on_progress=lambda txt:self.queue.put(('message',txt)))
                self.queue.put(('comparison',format_comparison(result)))
            except Exception as exc:
                failure=record_failure(exc,'compare-selected')
                self.queue.put(('comparison_error',f'Comparison failed ({failure.reason}). Incident {failure.incident_id}. See View logs.'))
            finally:self.queue.put(('compare_done',None))
        self.worker_thread=threading.Thread(target=worker,daemon=False)
        self.worker_thread.start()

    def start(self):
        if self.comparing:
            self.status.set('Selected-node comparison is running; wait until it finishes.')
            return
        if not self.save():return
        self.monitor_enabled=True
        self.schedule.arm(self.settings.refresh_minutes)
        self._update_monitor_buttons()
        if self.running:
            self.status.set('Auto timer armed. Current cycle will finish first; next due time starts from its completion.')
        else:
            self.status.set(f'Auto timer armed. First cycle in {self.settings.refresh_minutes} minutes of real elapsed time (sleep included).')

    def run_and_monitor(self):
        if self.running or self.comparing:
            self.status.set('Another operation is running. Enable auto timer separately to schedule its next cycle.')
            return
        if not self.save():return
        self.monitor_enabled=True
        self.schedule.arm(self.settings.refresh_minutes)
        self._update_monitor_buttons()
        self.launch(False,False)
        if not self.running:
            self.schedule.disarm();self.monitor_enabled=False
            self._update_monitor_buttons()
        else:
            self.status.set('Full cycle started now; automatic repeats will be scheduled after it finishes.')

    def stop(self):
        was_armed=self.monitor_enabled
        self.monitor_enabled=False;self.schedule.disarm();self.cancel.set()
        self._update_monitor_buttons()
        if self.running or self.comparing:
            self.status.set('Stop requested; active operation will stop at its next interruptible step. Previous results remain saved.')
        elif was_armed:
            self.status.set('Automatic monitoring timer disabled. No scan was running; previous exports remain saved.')
        elif request_cancel_active_cycle():
            owner=active_cycle_info()
            self.status.set(f'Stop requested for active monitor process {owner.get("pid","?")}.')
        else:
            self.status.set('No operation in this window. If an older app is still running, close that window first.')

    def run_once(self):self.launch(False,False)
    def update_only(self):self.launch(False,True)

    def launch(self,all_nodes,update_only):
        if self.running or self.comparing:
            self.status.set('An operation is already running in this window. Click Stop and wait for it to end before starting a new one.')
            return
        if self.connection.active and self.connection.mode=='tun' and not update_only:
            self.status.set('Disconnect TUN before full scanning: routed benchmark traffic would distort the results.')
            return
        if not self.save():return
        if not self.settings.subscription_url:
            messagebox.showwarning('No subscription','Enter an HTTPS URL or local subscription file.');return
        self.running=True;self.cancel.clear()
        self._update_monitor_buttons()
        self.scan_live={'feed':0,'latency':0,'speed':0,'baseline':0}
        self._seen_latency.clear();self._seen_speed.clear()
        self._update_usage_meter()
        # Isolate the cycle's settings from later user edits on the GUI thread.
        snapshot=copy.deepcopy(self.settings)
        event('gui-run-requested',all_nodes=all_nodes,update_only=update_only)
        source_id=subscription_fingerprint(snapshot.subscription_url)[:10]
        self.status.set(f'Requesting selected source #{source_id}. Previous run stays visible until it succeeds.')
        self.footer.set(f'Updating source #{source_id}; previous totals are NOT a result of this request.')
        self.worker_thread=threading.Thread(target=self.worker,args=(snapshot,all_nodes,update_only),daemon=False)
        self.worker_thread.start()

    def worker(self,settings,all_nodes,update_only):
        def progress(d):self.queue.put(('progress',d))
        def message(m):self.queue.put(('message',m))
        try:
            stats=run_cycle(settings,self.cancel,progress,message,all_nodes,update_only)
            if self.cancel.is_set():
                self.queue.put(('cancelled','Operation stopped; previous saved results preserved.'))
            else:
                if not update_only:
                    persist_stats(stats)
                self.queue.put(('finished',stats))
        except NoUsableMeasurements as exc:
            self.queue.put(('skipped',f'Scan skipped: {exc}. No results or exports were overwritten.'))
        except OperationCancelled:
            self.queue.put(('cancelled','Operation cancelled; previous working exports and saved statistics were retained.'))
        except CycleBusy:
            owner=active_cycle_info()
            if owner:
                reason=f'Another monitor process (PID {owner["pid"]}) owns the active cycle. Close it or click Stop here to request cancellation.'
            else:
                reason='An older monitor process still owns the cycle lock. Close the old app and allow its download to finish, then retry.'
            self.queue.put(('busy',reason))
        except Exception as exc:
            failure=exc if isinstance(exc,CycleFailure) else record_failure(exc,'gui-worker')
            self.queue.put(('error',f'Cycle failed at {failure.phase}: {failure.reason}. '
                                    f'Incident {failure.incident_id}. Click View logs.'))
        finally:self.queue.put(('ready',None))

    def load_previous_working(self):
        """Show last successful HTTPS pool (historical; never advertised as live)."""
        saved=read_working_snapshot()
        records=saved.get('nodes',[])
        if not isinstance(records,list):return
        loaded=0
        for entry in records[:50000]:
            try:
                outbound=entry['outbound']
                if not isinstance(outbound,dict):continue
                node=Node(str(entry['name']),str(entry['protocol']),outbound,
                          str(entry['source_kind']),str(entry.get('source_text','')))
                if node.id!=entry['id'] or not node.supported:continue
                self.nodes_by_id[node.id]=node
                self.row_state[node.id]={
                    'status':'Previous scan · '+str(entry.get('status','HTTPS passed')),
                    'latency':entry.get('latency'),'mbps':entry.get('mbps'),
                    'flow_mbps':entry.get('flow_mbps'),
                    'seconds':entry.get('seconds'),
                    'reliability':entry.get('reliability'),
                    'confirmed':entry.get('confirmed',False)}
                self.working_ids.add(node.id)
                self.working_tree.insert('','end',iid=node.id,values=self.row_values(node.id,working=True))
                loaded+=1
            except (ValueError,TypeError,KeyError,tk.TclError):
                continue
        if loaded:
            src=str(saved.get('source_id','?'))[:10]
            self.results_tabs.tab(1,text=f'Working nodes · Previous scan ({loaded})')
            self.footer.set(f'Historical working nodes loaded from pool #{src}; start a new cycle to refresh them.')

    def load_rows(self,nodes):
        if self._populate_after_id is not None:
            try:self.root.after_cancel(self._populate_after_id)
            except tk.TclError:pass
            self._populate_after_id=None
        self.rows_generation+=1
        generation=self.rows_generation
        self.nodes_by_id={n.id:n for n in nodes}
        self.row_state={n.id:{'status':'Untested' if n.supported else 'Unsupported (parser)'} for n in nodes}
        self.pending_rows=iter(nodes)
        self.live_passed=0;self.live_downloads=0;self.live_speed_attempts=0
        self.live_speed_seen=set();self.live_top=0.0
        self.scan_live={'feed':self.scan_live.get('feed',0),'latency':0,'speed':0,'baseline':0}
        self._seen_latency.clear();self._seen_speed.clear();self._update_usage_meter()
        self.tree.delete(*self.tree.get_children())
        self.working_tree.delete(*self.working_tree.get_children())
        self.working_ids.clear()
        self.results_tabs.tab(1,text='Working nodes · HTTPS passed (0)')
        self.stat_vars[0].set(str(len(nodes)));self.stat_vars[1].set(str(sum(n.supported for n in nodes)))
        for i in (2,3,4,5):self.stat_vars[i].set('—')
        def populate():
            self._populate_after_id=None
            if self.rows_generation!=generation:return
            for _ in range(300):
                try:n=next(self.pending_rows)
                except StopIteration:return
                self.tree.insert('','end',iid=n.id,values=self.row_values(n.id))
            self._populate_after_id=self.root.after(10,populate)
        self._populate_after_id=self.root.after(1,populate)

    def row_values(self,node_id,working=False):
        n=self.nodes_by_id[node_id];r=self.row_state.get(node_id,{})
        lat=r.get('latency');rate=r.get('mbps');flow=r.get('flow_mbps')
        sec=assess_outbound(n.outbound)
        return (r.get('working_rank','') if working else r.get('rank',''),n.name,n.protocol,
                sec.encryption, '—' if sec.score is None else str(sec.score),
                '—' if lat is None else f'{lat:.1f}',
                '—' if rate is None else f'{rate:.3f}',
                '—' if flow is None else f'{flow:.3f}',
                '—' if r.get('seconds') is None else f"{r['seconds']:.1f}",
                '—' if r.get('reliability') is None else f"{r['reliability']*100:.0f}%",
                'Yes' if r.get('confirmed') else 'No' if rate is not None else '—',
                r.get('status','Untested'))

    def update_row(self,node_id):
        if node_id not in self.nodes_by_id:return
        value=self.row_values(node_id)
        if self.tree.exists(node_id):self.tree.item(node_id,values=value)
        if self.working_tree.exists(node_id):self.working_tree.item(node_id,values=self.row_values(node_id,working=True))

    def _mark_working(self,node_id):
        if node_id not in self.nodes_by_id or node_id in self.working_ids:return
        self.working_ids.add(node_id)
        self.working_tree.insert('','end',iid=node_id,values=self.row_values(node_id,working=True))
        self.results_tabs.tab(1,text=f'Working nodes · HTTPS passed ({len(self.working_ids)})')
        self.sort_pending=True

    def _update_usage_meter(self):
        parts=self.scan_live
        total=sum(parts.values())
        def mib(value):return f'{max(0,int(value))/1048576:.3f}'
        self.stat_vars[6].set(mib(total))
        self.scan_usage_text.set('Scan HTTP ≥ '+mib(total)+' MiB   |   Feed '+mib(parts['feed'])+
                                 '   Latency '+mib(parts['latency'])+
                                 '   Speed '+mib(parts['speed'])+
                                 '   Baseline '+mib(parts['baseline'])+' MiB')

    def progress_event(self,v):
        action=v.get('event')
        if action=='scan-usage-feed':
            self.scan_live['feed']=max(0,int(v.get('bytes') or 0))
            self._update_usage_meter();return
        if action=='scan-usage-baseline':
            self.scan_live['baseline']=max(0,int(v.get('bytes') or 0))
            self._update_usage_meter();return
        if action=='scan-usage-final':
            for key in ('feed','latency','speed','baseline'):
                self.scan_live[key]=max(0,int(v.get(key) or 0))
            self._update_usage_meter();return
        if action=='nodes-loaded':
            self.load_rows(v['nodes']);return
        if action=='probe-start':
            for node_id in v['node_ids']:
                if node_id in self.row_state:self.row_state[node_id]['status']='Queued latency'
            return
        if action=='probe-result':
            node_id=v['node_id'];p=v['probe']
            if node_id not in self._seen_latency:
                self._seen_latency.add(node_id)
                self.scan_live['latency']+=(max(0,getattr(p,'http_sent_bytes',0))+
                                            max(0,getattr(p,'http_received_bytes',0)))
                self._update_usage_meter()
            if node_id not in self.row_state:return
            r=self.row_state[node_id]
            if p.ok:
                r['latency']=p.latency_ms;r['status']='Latency passed'
                self.live_passed+=1;self.stat_vars[2].set(str(self.live_passed))
                self._mark_working(node_id)
            else:
                r['core_error']=p.error if 'core' in p.error else ''
                r['status']=('Core rejected configuration' if p.error.startswith('core rejected:') else
                             'Core startup error' if p.error=='core runtime startup failed' else
                             'Latency failed')
            self.update_row(node_id);self.sort_pending=True
            return
        if action=='latency-finished':
            self.status.set(f"Latency checks finished: {v.get('passed',0)} successful. Selecting download candidates…")
            self.sort_pending=True;self._resort(force=True);return
        if action=='speed-selection':
            selected=set(v['node_ids']);cutoff=v['cutoff_ms']
            for node_id,r in self.row_state.items():
                if r.get('latency') is None:continue
                if node_id in selected:r['status']='Queued download'
                elif cutoff and r['latency']>=cutoff:r['status']='Slow-ping not sampled'
                else:r['status']='Not in top download candidates'
                self.update_row(node_id)
            self.footer.set(f"{v.get('eligible',0)} nodes below {cutoff or 'unlimited'} ms; "
                            f"{len(selected)} speed candidates incl. {v.get('exploratory',0)} above target.")
            return
        if action=='node-ranked':
            node_id=v['node_id']
            if node_id in self.row_state:
                r=self.row_state[node_id];r['reliability']=v['reliability'];r['status']=v['status']
                self.update_row(node_id)
            return
        if action=='speed-result':
            node_id=v['node_id'];speed=v['speed'];phase=v['speed_phase']
            key=(phase,node_id)
            if key not in self._seen_speed:
                self._seen_speed.add(key)
                self.scan_live['speed']+=max(0,int(speed.bytes_received))
                self._update_usage_meter()
            if phase=='preliminary' and node_id not in self.live_speed_seen:
                self.live_speed_seen.add(node_id);self.live_speed_attempts+=1
            if node_id not in self.row_state:return
            r=self.row_state[node_id]
            if speed.ok:
                was_ok=r.get('mbps') is not None
                r['mbps']=speed.mbps;r['seconds']=speed.seconds
                if phase=='confirmation':r['flow_mbps']=speed.flow_mbps
                r['status']=('Consistent flow (test host)' if speed.verified else 'Burst / intermittent flow') if phase=='confirmation' else 'Preliminary only'
                if phase=='confirmation':r['confirmed']=bool(speed.verified)
                if not was_ok:
                    self.live_downloads+=1
                if speed.verified:
                    self.live_top=max(self.live_top,speed.flow_mbps if speed.flow_mbps is not None else speed.mbps)
                    self.stat_vars[4].set(f'{self.live_top:.3f}')
            else:
                if r.get('mbps') is None:r['status']='Download failed'
                else:r['status']='Confirmation failed (preliminary retained)'
            self.stat_vars[3].set(f'{self.live_downloads}/{self.live_speed_attempts}')
            self.update_row(node_id);return
        # Regular phase counters still update the status line during long phases.
        if 'phase' in v:
            self.status.set(f"{v.get('phase')} — {v.get('done',0)}/{v.get('total',0)}"+
                            (f" | {v.get('passed')} connected" if 'passed' in v else ''))

    def poll(self):
        try:
            for _ in range(250):
                kind,v=self.queue.get_nowait()
                if kind=='client_progress':self.client_status.set(v)
                elif kind=='client_connected':
                    self.client_status.set(v)
                    if self._pending_connection is not None:
                        outbound,name,mode,metrics=self._pending_connection
                        self._active_connection=(copy.deepcopy(outbound),name,dict(metrics or {}))
                        try:
                            remember_connection(name,outbound,mode,metrics=metrics)
                            self.refresh_recent()
                        except (OSError,ValueError,TypeError):
                            self.footer.set('Connected, but recent-connection history could not be saved.')
                        self._pending_connection=None
                elif kind=='client_verified':self.client_status.set(v)
                elif kind=='client_disconnected':
                    self._active_connection=None
                    self.client_status.set(v)
                elif kind=='client_error':
                    self._pending_connection=None
                    if not self.connection.active:self._active_connection=None
                    self._sync_mode_to_live_connection()
                    self.client_status.set('Connection failed: '+v)
                elif kind=='client_rollback':
                    self._pending_connection=None
                    self._sync_mode_to_live_connection()
                    self.client_status.set(v)
                elif kind=='client_ready':
                    self.client_busy=False
                    if self.client_disconnect_after_busy:
                        self.client_disconnect_after_busy=False
                        self._deferred_mode=None
                        if self.connection.active:self.disconnect_client()
                    elif self._deferred_mode is not None:
                        self._deferred_mode=None
                        if self.connection.active:self._mode_changed()
                elif kind=='progress':self.progress_event(v)
                elif kind=='message':self.footer.set(v)
                elif kind=='finished':
                    self.present(v,update_table=not bool(self.nodes_by_id))
                    if not v.get('update_only'):
                        self.schedule.cycle_finished()
                    if v.get('update_only'):
                        sources=v.get('sources',[])
                        incomplete=[x for x in sources if x.get('state') in ('failed','cached-same-source')]
                        if incomplete:
                            self.status.set(f'PARTIAL: {len(sources)-len(incomplete)}/{len(sources)} feeds fresh; '
                                            f'{len(incomplete)} unavailable/cached. No proxy tests performed.')
                        else:
                            self.status.set(f'SUCCESS: {len(sources) or 1} source(s) parsed into pool '
                                            f'#{v.get("source_id","unknown")}. No proxy tests performed.')
                    elif v.get('subscription') in ('cached-same-source','combined-incomplete'):
                        self.status.set('WARNING: Some feeds unavailable. Cycle used older same-source data where possible.')
                    elif v.get('subscription') in ('recent-cache','combined-reused'):
                        self.status.set('Cycle complete. Recent successful subscriptions were reused (less than 60 minutes old).')
                    else:
                        self.status.set(f'Cycle complete for source #{v.get("source_id","unknown")}. Live results and exports available.')
                elif kind=='error':
                    self.status.set('Selected source NOT loaded. '+v)
                    self.footer.set(f'Previous shortlists/results preserved. Log: {LOG_FILE}')
                    if self.monitor_enabled:self.schedule.defer_failed()
                elif kind=='skipped':
                    if self.monitor_enabled:
                        self.schedule.defer_failed()
                        self.status.set(v+' Automatic monitoring retries in 5 minutes.')
                    else:
                        self.status.set(v)
                    self.footer.set('No validated results; previous rankings and all exports are preserved.')
                elif kind in ('busy','cancelled'):
                    self.status.set(v);self.footer.set('Saved results and existing exports were not changed.')
                    if self.monitor_enabled:self.schedule.defer_failed()
                elif kind=='comparison':
                    self.status.set('Selected-node comparison finished. Main rankings and exports were not changed.')
                    messagebox.showinfo('Two-destination comparison',v,parent=self.root)
                elif kind=='comparison_error':self.status.set(v)
                elif kind=='compare_done':self.comparing=False
                elif kind=='ready':
                    self.running=False
                    self._update_monitor_buttons()
        except queue.Empty:pass
        if self.connection.active and time.monotonic()-self._last_traffic_refresh>=0.7:
            self._last_traffic_refresh=time.monotonic()
            counters=self.connection.traffic()
            def rate(value):
                return f'{value/1048576:.2f} MB/s' if value>=1048576 else f'{value/1024:.1f} KB/s'
            def volume(value):
                return f'{value/1073741824:.2f} GiB' if value>=1073741824 else (
                    f'{value/1048576:.2f} MiB' if value>=1048576 else f'{value/1024:.1f} KiB')
            traffic=(f' | ↓ {rate(counters["down_bps"])} ↑ {rate(counters["up_bps"])}'
                     if counters['available'] else ' | Live traffic: connecting to core API…')
            totals=f' | Total ↓ {volume(counters["down"])} ↑ {volume(counters["up"])}'
            self.client_status.set(self.connection.status()+traffic+totals)
        if self.connection.reconcile():
            self.client_status.set('Connection ended unexpectedly. Windows proxy was restored if still owned by this app.')
        if self.sort_pending and time.monotonic()-self.last_sort>=3:
            self._resort()
        if self.monitor_enabled and not self.running and not self.comparing and self.schedule.ready():
            # Move the deadline before launching, even if validation fails. A
            # blocked/offline connection must not create a busy retry loop.
            self.schedule.defer_failed()
            if self.connection.active and self.connection.mode=='tun':
                self.status.set('Auto monitoring paused while TUN is active; preserves fair benchmark routing.')
            elif not outbound_route_present():
                self.status.set('Auto monitoring paused: no outbound network route. Next retry in 5 minutes. Prior files retained.')
                event('auto-monitor-paused',kind='no-ip-route')
            else:
                self.launch(False,False)
        if self.monitor_enabled and not self.running:
            remaining=self.schedule.remaining()
            self.timestamp.set(f'Auto refresh in {remaining//60}m {remaining%60}s (sleep counts)')
        self._update_monitor_buttons()
        self._poll_after_id=self.root.after(120,self.poll)

    def present(self,stats,update_table=False):
        if not stats:return
        shown_downloads=(f"{stats['speed_tested']}/{stats['speed_attempted']}"
                         if stats.get('speed_attempted') is not None else stats.get('speed_tested'))
        for var,val in zip(self.stat_vars,[stats.get('total'),stats.get('parsed'),stats.get('connected'),
                      shown_downloads,stats.get('fastest_mbps'),stats.get('baseline_mbps'),
                      stats.get('scan_payload_mib')]):
            var.set('—' if val is None else str(val))
        if update_table:
            self.tree.delete(*self.tree.get_children())
            for i,r in enumerate(stats.get('results',[]),1):
                self.tree.insert('','end',values=(i,r['name'],r['protocol'],
                      r.get('encryption','Unassessed'),r.get('security_score','—'),r['latency_ms'],
                      r['mbps'],r.get('flow_mbps','—') if r.get('flow_mbps') is not None else '—',
                      r.get('sample_seconds','—'),f"{r['reliability']*100:.0f}%",
                      'Yes' if r['confirmed'] else 'No',r['status']))
        if stats.get('time'):
            self.timestamp.set('Last cycle '+datetime.fromtimestamp(stats['time']).strftime('%Y-%m-%d %H:%M:%S'))
        exports=', '.join(stats.get('exports',{})) or 'previous shortlist retained'
        self.displayed_source_id=stats.get('source_id')
        source_state=stats.get('subscription','Previous saved results; source unknown')
        if source_state=='cached-same-source':source_state='STALE CACHE (same source; update failed)'
        if not self.displayed_source_id:
            source_state='PREVIOUS results — source identity unknown (pre-v1.0.11)'
        sources=stats.get('sources',[])
        unavailable=sum(x.get('state') in ('failed','cached-same-source') for x in sources)
        overview=f'{len(sources)} feed(s), {unavailable} missing/stale · ' if sources else ''
        self.footer.set(f"Pool: {overview}{source_state} #{self.displayed_source_id or '?'} • {stats.get('format','—')} • "
                        f"Unsupported: {stats.get('unsupported',0)} • duplicates: {stats.get('duplicates',0)} • "
                        f"Exports: {exports} • core: {stats.get('core_version','—')}")
        if stats.get('scan_payload_mib') is not None:
            today=round(daily_payload_bytes()/1048576,3)
            self.footer.set(self.footer.get()+f' • Scan HTTP ≥{stats["scan_payload_mib"]:.3f} MiB; today ≥{today:.3f} MiB (TLS/proxy overhead excluded)')
            self.scan_live={
                'feed':int(stats.get('feed_bytes') or 0),
                'latency':int(stats.get('latency_http_bytes') or 0),
                'speed':int(stats.get('speed_body_bytes',stats.get('bytes_downloaded',0)) or 0),
                'baseline':int(stats.get('baseline_body_bytes') or 0)}
            self._update_usage_meter()
        self.sort_pending=True


    def sort(self,column,tree=None):
        tree=tree or self._active_tree()
        working=tree is self.working_tree
        is_recent=tree is self.recent_tree
        field='recent_table_sort' if is_recent else 'working_table_sort' if working else 'table_sort'
        flag='recent_reverse' if is_recent else 'working_reverse' if working else 'reverse'
        if getattr(self,field)==column:setattr(self,flag,not getattr(self,flag))
        else:
            setattr(self,field,column)
            setattr(self,flag,column in ('download','flow'))
        self._resort(force=True,tree=tree)

    def _resort(self,force=False,tree=None):
        if not force and not self.sort_pending:return
        for current in ((tree,) if tree is not None else (self.tree,self.working_tree)):
            iids=current.get_children('')
            if not iids:continue
            working=current is self.working_tree
            recent=current is self.recent_tree
            col=self.recent_table_sort if recent else self.working_table_sort if working else self.table_sort
            reverse=self.recent_reverse if recent else self.working_reverse if working else self.reverse
            numeric=col in ('rank','security','latency','download','flow','sample','reliability')
            def key(iid):
                value=current.set(iid,col)
                if numeric:
                    try:
                        number=float(str(value).rstrip('%'))
                        return (0,-number if reverse else number)
                    except (ValueError,TypeError):return (1,0)
                return str(value).casefold()
            ordered=sorted(iids,key=key,reverse=reverse if not numeric else False)
            for i,iid in enumerate(ordered):
                if iid!=iids[i]:current.move(iid,'',i)
                if not recent and iid in self.row_state:
                    self.row_state[iid]['working_rank' if working else 'rank']=i+1
                    current.set(iid,'rank',str(i+1))
        self.sort_pending=False
        self.last_sort=time.monotonic()
    def close(self):
        if self._icon_map_binding:
            try:self.root.unbind('<Map>',self._icon_map_binding)
            except tk.TclError:pass
            self._icon_map_binding=None
        for attr in ('_icon_after_id','_dashboard_fit_after_id'):
            after_id=getattr(self,attr,None)
            if after_id is not None:
                try:self.root.after_cancel(after_id)
                except tk.TclError:pass
                setattr(self,attr,None)
        # Cancel the pending fitting callbacks before destroying Tcl widgets.
        self.monitor_enabled=False;self.schedule.disarm();self.cancel.set()
        self.connection._stop_requested.set()
        if self._populate_after_id is not None:
            try:self.root.after_cancel(self._populate_after_id)
            except tk.TclError:pass
            self._populate_after_id=None
        poll_id=getattr(self,'_poll_after_id',None)
        if poll_id is not None:
            try:self.root.after_cancel(poll_id)
            except tk.TclError:pass
            self._poll_after_id=None
        self.root.withdraw();self._finish_close()

    def _finish_close(self):
        if (self.worker_thread and self.worker_thread.is_alive()) or (self.client_thread and self.client_thread.is_alive()):
            self.root.after(250,self._finish_close)
        else:
            try:self.connection.stop()
            finally:self.root.destroy()


def main():
    if sys.platform=='win32':
        try:
            import ctypes
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID('IranRemainsConnected.Client.Scanner')
        except (AttributeError,OSError):pass
    root=tk.Tk();App(root);root.mainloop()
