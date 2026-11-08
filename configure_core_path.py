"""Installer helper: migrate a saved, version-specific core location if appropriate."""
from __future__ import annotations
import sys
from pathlib import Path
from iran_proxy_monitor.settings import Settings

new_core = Path(sys.argv[1]).resolve()
settings = Settings.load()
previous = settings.singbox_path.strip()
looks_packaged = ('iranproxymonitor' in previous.casefold().replace('-', '').replace('_', '')
                  and Path(previous).name.lower() == 'sing-box.exe'
                  and Path(previous).parent.name.lower() == 'bin')
if not previous or looks_packaged or not Path(previous).is_file():
    settings.singbox_path = str(new_core)
    settings.save()
    print('Dashboard sing-box path set to the installed core.')
else:
    print('Kept previously configured custom sing-box path.')
