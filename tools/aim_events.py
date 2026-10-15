"""Small silent event observer; no host, model, serial or client-control imports."""
import json
from pathlib import Path
import sys
from host_security import read_local_json
from provider_catalog import PROVIDERS
from session_activity import claude_event


def receive(root, provider='claude'):
    try:
        root=Path(root)
        config=read_local_json(root/'tools/aim_host.json',65536)
        selected=config.get('providers') if isinstance(config,dict) else None
        if (not isinstance(selected,list) or len(selected)>8 or
                any(not isinstance(p,str) or p not in PROVIDERS for p in selected) or
                len(set(selected))!=len(selected) or provider not in selected or provider not in ('claude','codex','zcode')): return 0
        from live_events import marker as live_marker, lifecycle_event
        marker=live_marker(root/'tools/activity',provider)
        if not marker['enabled']: return 0
        raw=sys.stdin.buffer.read(65537)
        if len(raw)<=65536:
            payload=json.loads(raw)
            if provider=='claude': claude_event(payload,root/'tools/activity',generation=marker['generation'])
            lifecycle_event(provider,payload,root/'tools/activity',generation=marker['generation'])
    except (ValueError,OSError,TypeError,RecursionError): pass
    return 0


def main():
    if sys.argv[1:]==['--check']: return 0
    options={'--claude-event':'claude','--codex-event':'codex','--zcode-event':'zcode'}
    if len(sys.argv)!=2 or sys.argv[1] not in options:return 0
    root=Path(sys.executable).resolve().parent if getattr(sys,'frozen',False) else Path(__file__).resolve().parents[1]
    return receive(root,options[sys.argv[1]])


if __name__=='__main__': sys.exit(main())
