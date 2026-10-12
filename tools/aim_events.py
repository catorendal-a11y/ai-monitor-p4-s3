"""Small silent event observer; no host, model, serial or client-control imports."""
import json
from pathlib import Path
import sys
from host_security import read_local_json
from provider_catalog import PROVIDERS
from session_activity import claude_event, link_marker


def receive(root):
    try:
        root=Path(root)
        config=read_local_json(root/'tools/aim_host.json',65536)
        selected=config.get('providers') if isinstance(config,dict) else None
        if (not isinstance(selected,list) or len(selected)>8 or
                any(not isinstance(p,str) or p not in PROVIDERS for p in selected) or
                len(set(selected))!=len(selected) or 'claude' not in selected): return 0
        marker=link_marker(root/'tools/activity')
        if not marker['enabled']: return 0
        raw=sys.stdin.buffer.read(65537)
        if len(raw)<=65536:
            claude_event(json.loads(raw),root/'tools/activity',generation=marker['generation'])
    except (ValueError,OSError,TypeError,RecursionError): pass
    return 0


def main():
    if sys.argv[1:]==['--check']: return 0
    if sys.argv[1:]!=['--claude-event']: return 0
    root=Path(sys.executable).resolve().parent if getattr(sys,'frozen',False) else Path(__file__).resolve().parents[1]
    return receive(root)


if __name__=='__main__': sys.exit(main())
