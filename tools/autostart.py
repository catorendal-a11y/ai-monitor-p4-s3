"""Start the host when this Windows user signs in.

One value named LimitBuddy under the current user's Run key: no administrator rights, shown in
Windows Settings > Apps > Startup. The value is only replaced or removed when it is recognizably
ours (the exact command shape written here), so another program's entry is never touched.
"""
import os
from pathlib import Path
import re
import sys

RUN_KEY = r'Software\Microsoft\Windows\CurrentVersion\Run'
VALUE_NAME = 'LimitBuddy'
_COMMAND = re.compile(r'"(?P<python>[^"]+)" "(?P<script>[^"]+)" --start-host')


class AutostartError(Exception):
    """A user-presentable reason; never carries paths from other programs' entries."""


def supported():
    return sys.platform == 'win32'


class RunKey:
    """The real registry value. Tests substitute an in-memory store."""
    def read(self):
        import winreg
        try:
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY) as key:
                value = winreg.QueryValueEx(key, VALUE_NAME)[0]
        except FileNotFoundError:
            return None
        return value if isinstance(value, str) else ''

    def write(self, value):
        import winreg
        with winreg.CreateKey(winreg.HKEY_CURRENT_USER, RUN_KEY) as key:
            winreg.SetValueEx(key, VALUE_NAME, 0, winreg.REG_SZ, value)

    def delete(self):
        import winreg
        try:
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY, 0, winreg.KEY_SET_VALUE) as key:
                winreg.DeleteValue(key, VALUE_NAME)
        except FileNotFoundError:
            pass


def _script_path(root):
    return Path(root).resolve() / 'tools' / 'aim_control.py'


def command_for(root, python=None):
    """The sign-in command: this installation's windowless Python starting its own host."""
    pythonw = Path(python or sys.executable).with_name('pythonw.exe')
    if not pythonw.is_file():
        raise AutostartError('No windowless Python was found for this installation.')
    return f'"{pythonw}" "{_script_path(root)}" --start-host'


def _parse(value):
    """(python, script) when the value has exactly the shape this module writes, else None."""
    match = _COMMAND.fullmatch(value or '')
    if not match:
        return None
    python, script = Path(match['python']), Path(match['script'])
    if python.name.lower() != 'pythonw.exe' or script.name.lower() != 'aim_control.py' or script.parent.name.lower() != 'tools':
        return None
    return python, script


def state(root, store=None):
    """off: no entry. on: starts this installation. other: ours, but starts another installation.
    foreign: an entry with our name that we did not write."""
    if store is None:
        if not supported():
            return 'off'  # no registry here, so nothing can be registered
        store = RunKey()
    value = store.read()
    if value is None:
        return 'off'
    parsed = _parse(value)
    if parsed is None:
        return 'foreign'
    same = os.path.normcase(str(parsed[1])) == os.path.normcase(str(_script_path(root)))
    return 'on' if same else 'other'


def enable(root, store=None, python=None):
    if store is None:
        if not supported():
            raise AutostartError('Start at sign-in is available on Windows only.')
        store = RunKey()
    if state(root, store) == 'foreign':
        raise AutostartError('Another program already uses the LimitBuddy startup entry. Nothing was changed.')
    command = command_for(root, python)
    try:
        store.write(command)  # an entry left by another installation is retargeted here
    except OSError:
        raise AutostartError('Windows did not allow changing the startup entry.') from None


def disable(root, store=None):
    """Remove the entry only when it starts this installation."""
    if store is None:
        if not supported():
            return
        store = RunKey()
    if state(root, store) != 'on':
        return
    try:
        store.delete()
    except OSError:
        raise AutostartError('Windows did not allow removing the startup entry.') from None


def apply(root, wanted, python=None):
    """Make the Windows startup entry match the saved setting."""
    if not supported():
        if wanted:
            raise AutostartError('Start at sign-in is available on Windows only.')
        return
    if wanted:
        enable(root, python=python)
    else:
        disable(root)
