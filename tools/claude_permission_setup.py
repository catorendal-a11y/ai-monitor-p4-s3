"""Explicit interactive-hook setup. Separate from observational hooks and runtime helper."""
from private_files import backup as private_backup
from claude_paths import config_root
from pathlib import Path
import copy
import time
from host_security import read_local_json
from telemetry_bridge import write_record


def hook(root, require_file=True):
    root = Path(root).resolve()
    helper = root / 'AI-Monitor-Permission.exe'
    if helper.is_symlink() or (require_file and not helper.is_file()) or helper.resolve().parent != root:
        raise ValueError('Permission helper missing. Install the complete Windows package.')
    # Documented exec form: no shell quoting, pipes or interpolation of tool arguments.
    return dict(type='command', command=str(helper), args=[], timeout=30)


def settings_path(home=None):
    directory = config_root(home)
    file = directory / 'settings.json'
    if directory.is_symlink() or file.is_symlink():
        raise ValueError('Claude settings must be a regular local file.')
    return file


def update(root, remove=False, home=None, opted_in=False):
    if type(remove) is not bool or type(opted_in) is not bool:
        raise ValueError('Invalid permission setup options')
    if not remove and not opted_in:
        raise ValueError('Save explicit PC permission opt-in before installing the helper.')
    expected = hook(root, require_file=not remove)
    path = settings_path(home)
    original = read_local_json(path, 65536) if path.exists() else {}
    if not isinstance(original, dict): raise ValueError('Invalid Claude settings; nothing changed.')
    document = copy.deepcopy(original)
    hooks = document.get('hooks', {})
    if not isinstance(hooks, dict): raise ValueError('Invalid Claude hooks; nothing changed.')
    entries = hooks.get('PermissionRequest', [])
    if (not isinstance(entries, list) or any(not isinstance(entry, dict)
            or not isinstance(entry.get('hooks'), list) for entry in entries)):
        raise ValueError('Invalid Claude permission hooks; nothing changed.')
    own_entry = dict(matcher='', hooks=[expected])
    if remove:
        kept = []
        for entry in entries:
            if entry.get('matcher', '') != '' or expected not in entry['hooks']:
                kept.append(entry); continue
            remaining = [item for item in entry['hooks'] if item != expected]
            if remaining or set(entry) - {'matcher', 'hooks'}:
                kept.append(dict(entry, hooks=remaining))
        if kept: hooks['PermissionRequest'] = kept
        else: hooks.pop('PermissionRequest', None)
    elif not any(entry.get('matcher', '') == '' and expected in entry['hooks'] for entry in entries):
        hooks['PermissionRequest'] = entries + [own_entry]
    if hooks: document['hooks'] = hooks
    else: document.pop('hooks', None)
    if document == original:
        return 'Permission helper already ' + ('removed.' if remove else 'linked.')
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        private_backup(path, path.with_name('settings.ai-monitor-permission-backup-' + str(time.time_ns()) + '.json'))
    write_record(path, document)
    return ('Permission helper removed; other Claude hooks and rules were preserved.' if remove else
            'Permission helper linked. Restart Claude Code. Physical decisions require both PC and display opt-in; '
            'unavailable or unsupported requests retain Claude permission handling. Existing hooks and rules remain in force.')


def state(root, home=None):
    try:
        expected = hook(root)
        path = settings_path(home)
        document = read_local_json(path, 65536) if path.exists() else {}
        entries = document.get('hooks', {}).get('PermissionRequest', [])
        if not isinstance(entries, list): return 'invalid'
        return 'installed' if any(isinstance(entry, dict) and entry.get('matcher', '') == ''
                                 and expected in entry.get('hooks', []) for entry in entries) else 'absent'
    except (ValueError, OSError, AttributeError, TypeError):
        return 'unavailable'
