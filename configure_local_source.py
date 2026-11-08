"""Set the local .txt as input without copying or modifying the source file.

Explicitly called by install-local.ps1 only; public installs keep existing settings.
"""
from __future__ import annotations
from pathlib import Path
import sys
from iran_proxy_monitor.settings import Settings, is_local_subscription


def configure(path_text: str) -> None:
    if not is_local_subscription(path_text):
        raise ValueError('A fully qualified local file path is required.')
    settings = Settings.load()
    settings.subscription_url = path_text
    settings.save()
    if Path(path_text).is_file():
        print('Local subscription configured; file found.')
    else:
        print('Local subscription path configured; file not found yet. Place the downloaded .txt there before running.')
    print('No subscription bytes were changed.')


if __name__ == '__main__':
    if len(sys.argv) != 2:
        sys.exit('Usage: configure_local_source.py ABSOLUTE_FILE_PATH')
    configure(sys.argv[1])
