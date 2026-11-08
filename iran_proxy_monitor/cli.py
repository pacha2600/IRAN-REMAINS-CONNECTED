"""Run a scheduled cycle without requiring the GUI."""
from __future__ import annotations
import argparse
import json
import sys
import threading
import traceback
from .settings import Settings
from .monitor import run_cycle,persist_stats,read_stats,NoUsableMeasurements
from .diagnostics import CycleFailure, record_failure, LOG_FILE

def main():
    p=argparse.ArgumentParser(description='Iran Proxy Monitor scheduled/command-line runner')
    p.add_argument('--once',action='store_true')
    p.add_argument('--all',action='store_true',help='Probe every supported node (may be slow)')
    p.add_argument('--update',action='store_true',help='Only update subscription cache')
    p.add_argument('--summary',action='store_true')
    a=p.parse_args()
    if a.summary:
        s=read_stats()
        print(json.dumps({k:s.get(k) for k in ('time','total','parsed','connected','speed_tested','fastest_mbps','exports')},indent=2))
        return
    s=Settings.load()
    if not s.subscription_url:
        print('First configure subscription URL in the GUI.',file=sys.stderr);sys.exit(2)
    try:
        results=run_cycle(s,threading.Event(),lambda d:None,lambda m:print(m),a.all,a.update)
        if not a.update:
            persist_stats(results)
        print('Connected:',results.get('connected'), 'Fastest Mbps:',results.get('fastest_mbps'))
    except NoUsableMeasurements as e:
        print(f'Cycle skipped; previous stats and exports preserved: {e}',file=sys.stderr)
        sys.exit(3)
    except Exception as e:
        failure=e if isinstance(e,CycleFailure) else record_failure(e, 'cli')
        print(f'Cycle error: {failure.phase}: {failure.reason} (incident {failure.incident_id}).',file=sys.stderr)
        print(f'Diagnostic log: {LOG_FILE}',file=sys.stderr)
        sys.exit(1)

if __name__=='__main__':main()
