"""Set the subscription source without downloading or modifying its bytes."""
from __future__ import annotations
import sys
from iran_proxy_monitor.settings import Settings

def configure(source: str, only_if_empty=False) -> None:
    settings = Settings.load()
    if only_if_empty and settings.subscription_url:
        print('Existing subscription source retained (installer did not overwrite it).')
        return
    settings.subscription_url = source
    settings.subscription_timeout_seconds = 300
    settings.save()
    print('Subscription URL configured; feed stall timeout: 300 seconds.')

if __name__ == '__main__':
    if len(sys.argv) < 2 or len(sys.argv) > 3 or (len(sys.argv)==3 and sys.argv[2]!='--if-empty'):
        raise SystemExit('Usage: configure_subscription_source.py URL [--if-empty]')
    configure(sys.argv[1], only_if_empty='--if-empty' in sys.argv[2:])
