"""Explicit local integration setup. Preserve unrelated client settings."""
from private_files import backup as private_backup
from claude_paths import config_root
import base64
import os
import re
from pathlib import Path
import sys
import time
from host_security import powershell_executable, read_local_json
from telemetry_bridge import write_record


def claude_command(root, option='--claude-statusline', *, interpreter=None):
    if option not in ('--claude-statusline','--claude-event','--codex-event'): raise ValueError('Unsupported event integration')
    observer=option in ('--claude-event','--codex-event')
    if getattr(sys, 'frozen', False) and interpreter is None:
        helper = root / ('AI-Monitor-Events.exe' if observer else 'AI-Monitor-Console.exe')
        if not helper.is_file(): raise ValueError('Console helper missing. Reinstall the complete release.')
        command = [str(helper), option]
    else:
        command = [str(interpreter or sys.executable), str(root / ('tools/aim_events.py' if observer else 'tools/aim_control.py')), option]
    if os.name == 'nt':
        expression = '$payload=[Console]::In.ReadToEnd(); $payload | & ' + ' '.join("'" + arg.replace("'", "''") + "'" for arg in command)
        if observer:
            expression=("$ProgressPreference='SilentlyContinue'; try { $buffer=[char[]]::new(65537); "
                '$count=[Console]::In.ReadBlock($buffer,0,$buffer.Length); '
                'if ($count -lt $buffer.Length) { $payload=[string]::new($buffer,0,$count); $payload | & '+
                ' '.join("'"+arg.replace("'","''")+"'" for arg in command)+
                ' *> $null } } catch {}; exit 0')
            if option=='--codex-event':
                # Stop/SubagentStop require neutral JSON. No context or decision fields.
                expression=expression.replace('exit 0',"[Console]::Out.WriteLine('{}'); exit 0")
        encoded = base64.b64encode(expression.encode('utf-16le')).decode('ascii')
        # Codex executes Windows command hooks through PowerShell. A quoted path
        # is a string expression there until the call operator invokes it.
        return ('& ' if option=='--codex-event' else '')+'"'+powershell_executable()+'" -NoProfile -EncodedCommand '+encoded
    import shlex
    suffix = (' >/dev/null 2>&1; printf \'{}\\n\'; exit 0' if option=='--codex-event' else
              ' >/dev/null 2>&1; exit 0' if observer else '')
    return shlex.join(command)+suffix


def event_process(root,provider):
    """Direct argv for clients with a process executor; never a shell or a decision."""
    if provider not in ('codex','claude','zcode'):raise ValueError('Unsupported observer')
    root=Path(root)
    if getattr(sys,'frozen',False):
        helper=root/'AI-Monitor-Events.exe'
        if not helper.is_file():raise ValueError('Observer helper missing. Reinstall the complete release.')
        return [str(helper),'--'+provider+'-event']
    return [sys.executable,str(root/'tools/aim_events.py'),'--'+provider+'-event']


def _zcode_hook(root):
    args=event_process(root,'zcode')
    return dict(type='process',command=args[0],args=args[1:],enabled=True,timeoutMs=2000)


def zcode_session_link(root,remove=False,home=None):
    """Explicit user-level observer setup; preserve unrelated hooks and global disablement."""
    from live_events import ZCODE_EVENTS,marker
    root=Path(root)
    settings=(Path.home() if home is None else Path(home))/'.zcode/cli/config.json'
    document=read_local_json(settings,65536) if settings.exists() else {}
    if not isinstance(document,dict):raise ValueError('Invalid ZCode settings; nothing changed.')
    hooks=document.get('hooks',{})
    if not isinstance(hooks,dict):raise ValueError('Invalid ZCode hooks; nothing changed.')
    events=hooks.get('events',{})
    if not isinstance(events,dict):raise ValueError('Invalid ZCode events; nothing changed.')
    expected=_zcode_hook(root);changed=False
    for event in sorted(ZCODE_EVENTS):
        entries=events.get(event,[])
        if not isinstance(entries,list) or any(not isinstance(e,dict) or not isinstance(e.get('hooks'),list) for e in entries):
            raise ValueError('Invalid ZCode hook entries; nothing changed.')
        if remove:
            kept=[]
            for entry in entries:
                if entry.get('matcher','')!='' or expected not in entry['hooks']:kept.append(entry);continue
                remaining=[h for h in entry['hooks'] if h!=expected]
                if remaining or set(entry)-{'matcher','hooks'}:kept.append(dict(entry,hooks=remaining))
                changed=True
            if kept:events[event]=kept
            else:events.pop(event,None)
        elif not any(e.get('matcher','')=='' and expected in e['hooks'] for e in entries):
            events[event]=entries+[{'hooks':[expected]}];changed=True
    activity=root/'tools/activity';marker_path=activity/'zcode-session-link.json'
    if remove:write_record(marker_path,dict(enabled=False,generation=time.time_ns()))
    if changed:
        # Only a new hook collection gets a global enable flag. Never activate existing custom hooks.
        if not remove and 'hooks' not in document:hooks['enabled']=True
        hooks['events']=events;document['hooks']=hooks
        settings.parent.mkdir(parents=True,exist_ok=True)
        if settings.exists():private_backup(settings,settings.with_name('config.ai-monitor-backup-'+str(time.time_ns())+'.json'))
        write_record(settings,document)
    if not remove and (changed or not marker(activity,'zcode')['enabled']):
        write_record(marker_path,dict(enabled=True,generation=time.time_ns()))
    return ('ZCode events removed; unrelated hooks preserved.' if remove else
            'ZCode events linked. Confirm Hooks is enabled in ZCode settings and start a new session. '
            'Only state and hashed identities are recorded; no context or tool decisions are returned.')


def zcode_session_state(root,home=None):
    from live_events import ZCODE_EVENTS,marker
    settings=(Path.home() if home is None else Path(home))/'.zcode/cli/config.json'
    try:
        doc=read_local_json(settings,65536) if settings.exists() else {}
        hooks=doc.get('hooks',{});events=hooks.get('events',{})
        if not isinstance(events,dict):return 'invalid'
        expected=_zcode_hook(root);found=0
        for event in ZCODE_EVENTS:
            entries=events.get(event,[])
            if not isinstance(entries,list):return 'invalid'
            found+=any(isinstance(e,dict) and e.get('matcher','')=='' and isinstance(e.get('hooks'),list)
                       and expected in e['hooks'] for e in entries)
        if found==len(ZCODE_EVENTS):
            if hooks.get('enabled') is not True:return 'hooks disabled in ZCode settings'
            return 'installed' if marker(Path(root)/'tools/activity','zcode')['enabled'] else 'link disabled / retry setup'
        return 'partial link' if found else 'not linked'
    except (ValueError,OSError,TypeError,AttributeError):return 'invalid'


def codex_session_state(root,home=None):
    from codex_support import codex_home
    from live_events import marker
    settings=(Path(home)/'.codex' if home is not None else codex_home())/'hooks.json'
    try:
        doc=read_local_json(settings,65536) if settings.exists() else {}
        hooks=doc.get('hooks',{})
        if not isinstance(hooks,dict):return 'invalid'
        expected={'type':'command','command':claude_command(Path(root),'--codex-event'),'timeout':2}
        found=0
        for event in CODEX_EVENTS:
            entries=hooks.get(event,[])
            if not isinstance(entries,list):return 'invalid'
            found+=any(isinstance(e,dict) and e.get('matcher','')=='' and isinstance(e.get('hooks'),list)
                       and expected in e['hooks'] for e in entries)
        if found==len(CODEX_EVENTS):
            return 'installed / review trust in Codex' if marker(Path(root)/'tools/activity','codex')['enabled'] else 'link disabled / retry setup'
        return 'partial or different observer / retry setup' if found else 'not linked'
    except (ValueError,OSError,TypeError,AttributeError):return 'invalid'


CODEX_EVENTS=('SessionStart','UserPromptSubmit','PreToolUse','PostToolUse','PermissionRequest',
              'SubagentStart','SubagentStop','Stop','Interrupt','SessionEnd')


def _legacy_codex_hook(hook,root):
    """Recognize only a byte-exact generated wrapper for this installation's source helper."""
    if (os.name!='nt' or not isinstance(hook,dict) or set(hook)!={'type','command','timeout'} or
            hook.get('type')!='command' or type(hook.get('timeout')) is not int or hook['timeout']!=2 or
            not isinstance(hook.get('command'),str)):return False
    try:
        current=claude_command(Path(root),'--codex-event')
        if current.startswith('& ') and hook['command']==current.removeprefix('& '):return True
        expression=base64.b64decode(hook['command'].rsplit(' ',1)[1],validate=True).decode('utf-16le')
        for candidate in re.findall(r"'([^']*python\.exe)'",expression,flags=re.IGNORECASE):
            if Path(candidate).is_absolute():
                expected=claude_command(Path(root),'--codex-event',interpreter=candidate)
                if hook['command'] in (expected,expected.removeprefix('& ')):return True
    except (ValueError,UnicodeError,IndexError):pass
    return False


def codex_session_link(root, remove=False, home=None):
    """Explicit setup only. Preserve unrelated hooks; never write hook trust or start Codex."""
    from codex_support import codex_home
    base=Path(home)/'.codex' if home is not None else codex_home()
    settings=base/'hooks.json'
    document=read_local_json(settings,65536) if settings.exists() else {}
    if not isinstance(document,dict): raise ValueError('Invalid Codex hooks; nothing changed.')
    hooks=document.get('hooks',{})
    if not isinstance(hooks,dict): raise ValueError('Invalid Codex hook collection; nothing changed.')
    expected={'type':'command','command':claude_command(Path(root),'--codex-event'),'timeout':2}
    changed=False
    for event in CODEX_EVENTS:
        entries=hooks.get(event,[])
        if (not isinstance(entries,list) or any(not isinstance(entry,dict) or
                not isinstance(entry.get('hooks'),list) for entry in entries)):
            raise ValueError('Invalid Codex hook entries; nothing changed.')
        if not remove:
            migrated=[]
            for entry in entries:
                replacements=[expected if entry.get('matcher','')=='' and _legacy_codex_hook(h,root) else h for h in entry['hooks']]
                if replacements!=entry['hooks']:changed=True
                migrated.append(dict(entry,hooks=replacements))
            entries=migrated
            if entries:hooks[event]=entries
        if remove:
            kept=[]
            for entry in entries:
                owned=entry.get('matcher','')=='' and any(h==expected or _legacy_codex_hook(h,root) for h in entry['hooks'])
                if not owned: kept.append(entry); continue
                remaining=[hook for hook in entry['hooks'] if hook!=expected and not _legacy_codex_hook(hook,root)]
                if remaining or set(entry)-{'matcher','hooks'}: kept.append(dict(entry,hooks=remaining))
                changed=True
            if kept: hooks[event]=kept
            else: hooks.pop(event,None)
        elif not any(entry.get('matcher','')=='' and expected in entry['hooks'] for entry in entries):
            hooks[event]=entries+[{'hooks':[expected]}];changed=True
    from live_events import marker
    activity=Path(root)/'tools/activity'
    marker_path=activity/'codex-session-link.json'
    if remove: write_record(marker_path,dict(enabled=False,generation=time.time_ns()))
    if changed:
        if hooks: document['hooks']=hooks
        else: document.pop('hooks',None)
        settings.parent.mkdir(parents=True,exist_ok=True)
        if settings.exists(): private_backup(settings,settings.with_name('hooks.ai-monitor-backup-'+str(time.time_ns())+'.json'))
        write_record(settings,document)
    if not remove and (changed or not marker(activity,'codex')['enabled']):
        write_record(marker_path,dict(enabled=True,generation=time.time_ns()))
    return ('Codex events removed; unrelated hooks preserved.' if remove else
            'Codex events linked. Review and trust these hooks in Codex /hooks, then restart the session. '
            'The observer returns no context or permission decision. No model session was started.')


def claude_bridge(root, remove=False, home=None):
    settings = config_root(home) / 'settings.json'
    document = read_local_json(settings, 65536) if settings.exists() else {}
    if not isinstance(document, dict): raise ValueError('Claude settings are invalid; nothing changed.')
    expected = {'type': 'command', 'command': claude_command(root)}
    current = document.get('statusLine')
    if remove:
        if current != expected: raise ValueError('This installation does not own the statusline. Existing settings were preserved.')
        del document['statusLine']
    elif current == expected:
        return 'Claude quota link is already installed. Use Claude Code to receive fresh quota data.'
    elif current:
        raise ValueError('Existing custom Claude statusline preserved. Remove it in Claude settings or keep local activity only.')
    else:
        document['statusLine'] = expected
    settings.parent.mkdir(parents=True, exist_ok=True)
    if settings.exists():
        private_backup(settings, settings.with_name('settings.ai-monitor-backup-' + str(time.time_ns()) + '.json'))
    write_record(settings, document)
    return ('Claude quota link removed. Local activity remains available.' if remove else
            'Claude quota link installed. Use Claude Code to receive fresh data. A private settings backup is on this PC.')


def claude_link_state(root, home=None):
    """Read-only status of this installation's quota link; never prints settings content."""
    settings = config_root(home) / 'settings.json'
    try:
        document = read_local_json(settings, 65536) if settings.exists() else {}
    except (ValueError, OSError):
        return 'invalid'
    if not isinstance(document, dict):
        return 'invalid'
    current = document.get('statusLine')
    try:
        expected = {'type': 'command', 'command': claude_command(root)}
    except ValueError:
        return 'unknown'
    if current == expected:
        return 'installed'
    return 'custom' if current else 'absent'


def _host_quota_report(running, state):
    """A saved key or installed CLI proves nothing; classify the host's freshest report."""
    if state == 'ready': return 'verified'
    if state == 'unavailable': return 'failed'
    return 'pending-running' if running else 'pending-stopped'


CLAUDE_EVENTS = ('SessionStart','UserPromptSubmit','PreToolUse','PostToolUse',
                 'PermissionRequest','Notification','Stop','StopFailure','SessionEnd','SubagentStart','SubagentStop',
                 'PostToolUseFailure','PermissionDenied','TeammateIdle','TaskCreated','TaskCompleted')


def claude_session_link(root, remove=False, home=None):
    """Append/remove only this installation's observational command hooks."""
    settings=config_root(home)/'settings.json'
    document=read_local_json(settings,65536) if settings.exists() else {}
    if not isinstance(document,dict): raise ValueError('Invalid Claude settings; nothing changed.')
    hooks=document.get('hooks',{})
    if not isinstance(hooks,dict): raise ValueError('Invalid Claude hooks; nothing changed.')
    expected={'type':'command','command':claude_command(root,'--claude-event'),'timeout':2}
    changed=False
    for event in CLAUDE_EVENTS:
        entries=hooks.get(event,[])
        if not isinstance(entries,list) or any(not isinstance(e,dict) or not isinstance(e.get('hooks'),list) for e in entries):
            raise ValueError('Invalid Claude hook entries; nothing changed.')
        matcher='permission_prompt|elicitation_dialog|agent_needs_input' if event=='Notification' else ''
        if remove:
            kept=[]
            for entry in entries:
                owned=entry.get('matcher','')==matcher and expected in entry['hooks']
                if not owned: kept.append(entry); continue
                remaining=[h for h in entry['hooks'] if h!=expected]
                if remaining or set(entry)-{'matcher','hooks'}: kept.append(dict(entry,hooks=remaining))
                changed=True
            if kept: hooks[event]=kept
            else: hooks.pop(event,None)
        elif not any(entry.get('matcher','')==matcher and expected in entry['hooks'] for entry in entries):
            hooks[event]=entries+[{'matcher':matcher,'hooks':[expected]}]
            changed=True
    from session_activity import link_marker
    marker_path=root/'tools/activity/claude-session-link.json'
    if remove:
        # Invalidates old/in-flight observations before removing the commands.
        write_record(marker_path,{'enabled':False,'generation':time.time_ns()})
    if not changed:
        if not remove and not link_marker(root/'tools/activity')['enabled']:
            write_record(marker_path,{'enabled':True,'generation':time.time_ns()})
        return 'Claude session events already '+('removed.' if remove else 'linked. Restart Claude Code to activate them.')
    if hooks: document['hooks']=hooks
    else: document.pop('hooks',None)
    settings.parent.mkdir(parents=True,exist_ok=True)
    if settings.exists(): private_backup(settings,settings.with_name('settings.ai-monitor-backup-'+str(time.time_ns())+'.json'))
    write_record(settings,document)
    if not remove: write_record(marker_path,{'enabled':True,'generation':time.time_ns()})
    return ('Claude session events removed; other hooks were preserved.' if remove else
            'Claude session events linked. Restart Claude Code. Hooks only record state; they return no permission decision.')


def setup_report(root, home=None):
    """Structured, source-specific readiness; no model/USB requests or writes."""
    from aim_control import local_config, owned_hosts
    from codex_support import codex_command
    from host_status import read_status
    from provider_catalog import PROVIDERS
    from token_activity import TokenReporter
    from session_activity import summary
    from live_events import live_agents
    config=local_config(root)
    reporter=TokenReporter(providers=config['providers'],activity_dir=root/'tools/activity',home=home)
    sample=reporter.poll()
    processes=owned_hosts(root)
    health=read_status(root,{p.pid for p in processes}) if processes else None
    states=health['providers'] if health else {}
    session_rows=summary(root/'tools/activity',config['providers'])['providers']
    observed=live_agents(root/'tools/activity',config['providers'])
    live=bool(health and health['state']=='connected' and health.get('board')==config.get('board')
              and config['port'] in ('auto',health.get('port')))
    results=[]
    for provider in config['providers']:
        readable=bool(sample['sources'] & PROVIDERS[provider][1])
        quota=_host_quota_report(bool(processes),states.get(provider))
        if provider=='codex': next_step=_codex_extra(bool(codex_command()),quota)
        elif provider=='zcode': next_step=_zcode_extra(_zcode_key_source(config),quota)
        elif provider=='claude': next_step=_claude_extra(claude_link_state(root,home))
        elif provider in ('gemini','opencode'): next_step='Use the official client once, then check again. This integration does not report remaining account quota.'
        else: next_step=_bridge_extra(provider,readable)
        event_state=({'claude':claude_session_state,'codex':codex_session_state,
                     'zcode':zcode_session_state}[provider](root,home) if provider in ('claude','codex','zcode') else 'unsupported')
        from host_status import live_status_text
        results.append(dict(provider=provider,activity='readable' if readable else 'missing',
            quota=quota if provider in ('codex','zcode','claude') else 'unsupported',
            display=('source-echoed' if live and type(health.get('display_sources')) is int
                     and health['display_sources'] & PROVIDERS[provider][1]
                     and type(health.get('display_sources_at')) in (int,float)
                     and 0<=time.time()-health['display_sources_at']<=35 else 'connected' if live else 'unconfirmed'),
            sessions='reporting' if any(r['provider']==provider for r in session_rows+observed) else
                     'linked / waiting for events' if event_state=='installed' else event_state,
            events=event_state,live_usb=live_status_text(health),
            next_step=next_step))
    return results


def observer_masks(root,providers,home=None):
    """(selected, linked) provider bits for the selected AIs that can have session observers.

    Only a verified hook installation counts as linked: an enabled marker left behind by a
    migrated folder, or settings that cannot be read, say nothing about whether events will come."""
    from provider_catalog import PROVIDERS
    checks={'claude':claude_session_state,'codex':codex_session_state,'zcode':zcode_session_state}
    selected=linked=0
    for provider in providers:
        check=checks.get(provider)
        if check is None:continue
        bit=PROVIDERS[provider][1]
        selected|=bit
        if check(root,home)=='installed':linked|=bit
    return selected,linked


def claude_session_state(root,home=None):
    settings=config_root(home)/'settings.json'
    try:
        document=read_local_json(settings,65536) if settings.exists() else {}
        if not isinstance(document,dict) or not isinstance(document.get('hooks',{}),dict): return 'invalid'
        hooks=document.get('hooks',{})
        expected={'type':'command','command':claude_command(root,'--claude-event'),'timeout':2}
        found=0
        for event in CLAUDE_EVENTS:
            entries=hooks.get(event,[])
            if not isinstance(entries,list): return 'invalid'
            matcher='permission_prompt|elicitation_dialog|agent_needs_input' if event=='Notification' else ''
            found+=any(isinstance(e,dict) and e.get('matcher','')==matcher
                       and isinstance(e.get('hooks'),list) and expected in e['hooks'] for e in entries)
        if found==len(CLAUDE_EVENTS):
            if document.get('disableAllHooks') is True: return 'hooks disabled in Claude settings'
            from session_activity import link_marker
            return 'installed' if link_marker(root/'tools/activity')['enabled'] else 'link disabled / retry setup'
        return 'partial link' if found else 'not linked'
    except (ValueError,OSError,TypeError): return 'invalid'


def _codex_extra(cli_found, report):
    if report == 'verified':
        if cli_found:
            return 'Official CLI found; the running host last received account quota successfully.'
        # The legacy file login can also supply quota; keep the host's observed success.
        return ('The running host last received account quota, but the CLI is not found now. A legacy file login can also supply quota. '
                'Install / sign in Codex in AI setup for the supported account interface.')
    if not cli_found:
        if report == 'pending-running':
            return ('Official CLI missing. The host is running but has not reported Codex yet; '
                    'check Host settings > Live provider health or the Host log.')
        return ('Official CLI missing. Open Install / sign in Codex in AI setup (console: Provider integration help) '
                'to install and sign in, then start the host and check its quota report.')
    return {
        'failed': 'Official CLI found, but the running host could not read quota. Check the Host log and repeat '
                  'Install / sign in Codex; quota requires a ChatGPT-backed login, and API-key-only mode has no plan quota.',
        'pending-running': 'Official CLI found. The host is running but has not reported Codex yet; '
                           'check Host settings > Live provider health or the Host log.',
        'pending-stopped': 'Official CLI found. This check does not verify sign-in: run Install / sign in Codex, or '
                           'start the host and read Host settings > Live provider health. Quota requires a ChatGPT-backed '
                           'login; API-key-only mode has no plan quota.',
    }[report]


def _zcode_key_source(config):
    """Mirror the host's precedence: a present ZAI_API_KEY entry overrides the saved key."""
    if 'ZAI_API_KEY' in os.environ:
        return 'environment' if os.environ['ZAI_API_KEY'].strip() else 'overridden'
    return 'saved' if config.get('zai_key') else 'none'


def _zcode_extra(source, report):
    if source == 'none':
        return ('For quota percentages, save your own Z.AI coding-plan key in AI setup; local activity needs no key. '
                "ZCode's own encrypted login is not imported.")
    if source == 'overridden':
        return ('An empty ZAI_API_KEY variable overrides AI setup in this PC\'s environment, so the host '
                'uses no key even if one is saved. Fill or remove that variable to use a key for quota.')
    provided = ("A Z.AI key is provided by this PC's ZAI_API_KEY environment variable, not saved by the app"
                if source == 'environment' else 'A Z.AI key is saved in AI setup')
    return {
        'verified': provided + '; the running host last received plan quota.',
        'failed': provided + ', but the running host could not read quota. Check the Host log; replace a wrong or '
                  'expired key, and let rate limiting clear through the host\'s automatic backoff.',
        'pending-running': provided + '; the host is running but has not reported ZCode yet. '
                           'Check Host settings > Live provider health.',
        'pending-stopped': provided + '. Quota is not verified yet: start the host, then read Host settings > '
                           'Live provider health. Local activity needs no key.',
    }[report]


def _claude_extra(link):
    return {
        'installed': 'Quota link installed. Use Claude Code; its statusline supplies fresh quota for about five minutes.',
        'custom': 'A custom Claude statusline exists and is preserved; the quota link cannot be added automatically. '
                  'Local activity still works; docs/PROVIDERS.md explains forwarding quota from your script.',
        'absent': 'Quota link not installed yet: click Link Claude quota for subscription windows, then restart Claude Code.',
        'invalid': 'Claude settings are unreadable; the quota link cannot be checked. Local activity still works.',
        'unknown': 'Quota link state unknown on this installation; reinstall the complete package if Claude quota is needed.',
    }[link]


def _bridge_extra(provider, readable):
    if readable:
        return 'Numeric bridge is reporting; the companion animates from forwarded counters. Account quota remains unavailable.'
    return ('Numeric bridge required: forward cumulative session tokens to nova --ingest ' + provider +
            ' (source-only checkouts: python tools/aim_control.py --ingest ' + provider + '). '
            'Selection alone cannot read this editor; see docs/PROVIDERS.md.')


def readiness(root, emit, home=None):
    from aim_control import local_config, owned_hosts
    from codex_support import codex_command
    from host_status import read_status
    from provider_catalog import PROVIDERS
    from token_activity import TokenReporter
    config = local_config(root)
    reporter = TokenReporter(providers=config['providers'], activity_dir=root/'tools/activity')
    sample = reporter.poll()
    # A fresh host report proves quota was last received, not that the current
    # key or CLI configuration produced it; report observations, not assumptions.
    processes = owned_hosts(root)
    health = read_status(root, {process.pid for process in processes}) if processes else None
    states = health['providers'] if health else {}
    for provider in config['providers']:
        name, bit, _ = PROVIDERS[provider]
        readable = bool(sample['sources'] & bit)
        if provider in ('copilot', 'cursor', 'antigravity'):
            source = 'Bridge token source readable.' if readable else 'No bridge data received yet.'
        else:
            source = 'Local token source readable.' if readable else 'No readable token source yet. Use the client once, then check again.'
        report = _host_quota_report(bool(processes), states.get(provider))
        if provider == 'codex':
            extra = _codex_extra(bool(codex_command()), report)
        elif provider == 'zcode':
            extra = _zcode_extra(_zcode_key_source(config), report)
        elif provider == 'claude':
            extra = _claude_extra(claude_link_state(root, home))
        elif provider in ('gemini', 'opencode'):
            extra = 'Activity-only integration: local tokens animate the companion; remaining account quota is unavailable in this integration.'
        else:
            extra = _bridge_extra(provider, readable)
        emit(name + ': ' + source + ' ' + extra)
    emit('This check read local numeric usage and configuration state only. It did not contact a model, flash the display or change client settings.')
