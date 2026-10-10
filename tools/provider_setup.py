"""Explicit local integration setup. Preserve unrelated client settings."""
import base64
import os
from pathlib import Path
import shutil
import sys
import time
from host_security import powershell_executable, read_local_json
from telemetry_bridge import write_record


def claude_command(root):
    if getattr(sys, 'frozen', False):
        helper = root / 'AI-Monitor-Console.exe'
        if not helper.is_file(): raise ValueError('Console helper missing. Reinstall the complete release.')
        command = [str(helper), '--claude-statusline']
    else:
        command = [sys.executable, str(root / 'tools/aim_control.py'), '--claude-statusline']
    if os.name == 'nt':
        expression = '$payload=[Console]::In.ReadToEnd(); $payload | & ' + ' '.join("'" + arg.replace("'", "''") + "'" for arg in command)
        encoded = base64.b64encode(expression.encode('utf-16le')).decode('ascii')
        return '"' + powershell_executable() + '" -NoProfile -EncodedCommand ' + encoded
    import shlex
    return shlex.join(command)


def claude_bridge(root, remove=False, home=None):
    settings = (Path.home() if home is None else Path(home)) / '.claude/settings.json'
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
        shutil.copy2(settings, settings.with_name('settings.ai-monitor-backup-' + str(time.time_ns()) + '.json'))
    write_record(settings, document)
    return ('Claude quota link removed. Local activity remains available.' if remove else
            'Claude quota link installed. Use Claude Code to receive fresh data. A private settings backup is on this PC.')


def claude_link_state(root, home=None):
    """Read-only status of this installation's quota link; never prints settings content."""
    settings = (Path.home() if home is None else Path(home)) / '.claude/settings.json'
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
    return ('Numeric bridge required: forward cumulative session tokens to AI-Monitor-Console.exe --ingest ' + provider +
            ' (source installs: python tools/aim_control.py --ingest ' + provider + '). '
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
