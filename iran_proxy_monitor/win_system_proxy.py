"""Reversible *per-user WinINet* proxy setting with stale-crash recovery.

Only ProxyEnable and ProxyServer are changed. Existing PAC settings are not
replaced; we reject the system mode when a PAC URL is active.
"""
from __future__ import annotations

import ctypes
import json
import os
from pathlib import Path
import tempfile

from .settings import DATA_DIR

KEY = r'Software\Microsoft\Windows\CurrentVersion\Internet Settings'
RESTORE_FILE = DATA_DIR / 'client-system-proxy-restore.json'


def is_administrator() -> bool:
    if os.name != 'nt':return False
    try:return bool(ctypes.windll.shell32.IsUserAnAdmin())
    except Exception:return False


def _read_values():
    import winreg
    values={}
    with winreg.OpenKey(winreg.HKEY_CURRENT_USER,KEY,0,winreg.KEY_READ) as key:
        for name in ('ProxyEnable','ProxyServer'):
            try:
                value,kind=winreg.QueryValueEx(key,name)
                values[name]={'present':True,'value':value,'kind':kind}
            except FileNotFoundError:
                values[name]={'present':False}
        try:
            pac,_=winreg.QueryValueEx(key,'AutoConfigURL')
        except FileNotFoundError:
            pac=''
    return values,str(pac)


def _write_values(values):
    import winreg
    with winreg.OpenKey(winreg.HKEY_CURRENT_USER,KEY,0,winreg.KEY_SET_VALUE) as key:
        for name,item in values.items():
            if item['present']:
                winreg.SetValueEx(key,name,0,int(item['kind']),item['value'])
            else:
                try:winreg.DeleteValue(key,name)
                except FileNotFoundError:pass
    _notify()


def _notify():
    # Inform WinINet/Windows Settings of changed per-user Internet options.
    if os.name != 'nt':return
    internet_set_option=ctypes.windll.wininet.InternetSetOptionW
    for option in (39,37):
        internet_set_option(None,option,None,0)


def _pid_alive(pid: int) -> bool:
    if os.name != 'nt' or pid <= 0:return False
    handle=ctypes.windll.kernel32.OpenProcess(0x1000,False,pid)
    if not handle:return False
    try:
        exit_code=ctypes.c_ulong()
        if not ctypes.windll.kernel32.GetExitCodeProcess(handle,ctypes.byref(exit_code)):
            return False
        return exit_code.value==259  # STILL_ACTIVE
    finally:ctypes.windll.kernel32.CloseHandle(handle)


def _atomic_state(data):
    RESTORE_FILE.parent.mkdir(parents=True,exist_ok=True)
    fd,name=tempfile.mkstemp(prefix='proxy-backup-',suffix='.tmp',dir=RESTORE_FILE.parent)
    try:
        with os.fdopen(fd,'w',encoding='utf-8') as f:json.dump(data,f)
        try:os.chmod(name,0o600)
        except OSError:pass
        os.replace(name,RESTORE_FILE)
    finally:
        if os.path.exists(name):os.unlink(name)


class WindowsProxySwitch:
    def enable(self, port: int):
        if os.name != 'nt':
            raise RuntimeError('Windows system proxy is only available on Windows.')
        self.recover_stale()
        if RESTORE_FILE.is_file():
            raise RuntimeError('An existing client session owns the Windows proxy settings.')
        snapshot,pac=_read_values()
        if pac.strip():
            raise RuntimeError('A Windows PAC/automatic proxy script is configured. Disable it first, or use Manual proxy.')
        expected=f'127.0.0.1:{port}'
        state={'owner_pid':os.getpid(),'expected':expected,'snapshot':snapshot}
        _atomic_state(state)  # record backup BEFORE altering Windows settings
        try:
            _write_values({'ProxyEnable':{'present':True,'value':1,'kind':4},
                           'ProxyServer':{'present':True,'value':expected,'kind':1}})
        except Exception:
            self.restore(overwrite=True)
            raise

    def restore(self, force: bool=False, overwrite: bool=False):
        if os.name != 'nt' or not RESTORE_FILE.is_file():return
        state=json.loads(RESTORE_FILE.read_text('utf-8'))
        if not force and int(state.get('owner_pid',-1))!=os.getpid():
            return  # another still-running monitor owns this snapshot
        current,_=_read_values()
        # Respect changes by Karing or another app while our client ran.
        # overwrite=True is used ONLY to roll back a partial enable failure.
        if (overwrite or (current['ProxyEnable'].get('value')==1 and
            current['ProxyServer'].get('value')==state.get('expected'))):
            _write_values(state['snapshot'])
        # Keep the backup on I/O/registry error for a subsequent recovery.
        RESTORE_FILE.unlink(missing_ok=True)

    def recover_stale(self):
        if os.name != 'nt' or not RESTORE_FILE.is_file():return
        state=json.loads(RESTORE_FILE.read_text('utf-8'))
        if not _pid_alive(int(state.get('owner_pid',0))):
            self.restore(force=True)
