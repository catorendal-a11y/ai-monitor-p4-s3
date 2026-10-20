"""Start at Windows sign-in: one current-user Run value, never touching entries that are not ours."""
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
import uuid
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools'))
import aim_control as control
import aim_host as host
import autostart
import desktop_support as desktop
from host_status import FLAGS, validate_options


class MemoryStore:
    """Stands in for HKCU\\...\\Run so no test touches the real registry."""
    def __init__(self, value=None):
        self.value = value; self.writes = []

    def read(self):
        return self.value

    def write(self, value):
        self.value = value; self.writes.append(value)

    def delete(self):
        self.value = None


class AutostartTestCase(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name)
        self.python = self.base / 'runtime' / 'python.exe'
        self.python.parent.mkdir(); self.python.write_bytes(b''); self.python.with_name('pythonw.exe').write_bytes(b'')
        self.root = self.base / 'LimitBuddy' / 'app-new'
        (self.root / 'tools').mkdir(parents=True)
        self.other = self.base / 'LimitBuddy' / 'app-old'

    def command(self, root=None):
        return autostart.command_for(root or self.root, python=self.python)


class CommandTests(AutostartTestCase):
    def test_command_starts_this_installation_without_a_console_window(self):
        pythonw = self.python.with_name('pythonw.exe')
        script = self.root.resolve() / 'tools' / 'aim_control.py'
        self.assertEqual(self.command(), f'"{pythonw}" "{script}" --start-host')

    def test_missing_windowless_python_is_an_error_not_a_broken_entry(self):
        self.python.with_name('pythonw.exe').unlink()
        with self.assertRaises(autostart.AutostartError):
            self.command()


class StateTests(AutostartTestCase):
    def test_states(self):
        self.assertEqual(autostart.state(self.root, MemoryStore()), 'off')
        self.assertEqual(autostart.state(self.root, MemoryStore(self.command())), 'on')
        self.assertEqual(autostart.state(self.root, MemoryStore(self.command(self.other))), 'other')
        for foreign in ('notepad.exe', '"C:\\x\\tool.exe" --start-host', '"C:\\x\\pythonw.exe" "C:\\x\\other.py" --start-host',
                        self.command() + ' --extra'):
            self.assertEqual(autostart.state(self.root, MemoryStore(foreign)), 'foreign', foreign)


class EnableDisableTests(AutostartTestCase):
    def test_enable_writes_the_command(self):
        store = MemoryStore(); autostart.enable(self.root, store, python=self.python)
        self.assertEqual(store.value, self.command())

    def test_enable_retargets_an_entry_left_by_another_installation(self):
        store = MemoryStore(self.command(self.other)); autostart.enable(self.root, store, python=self.python)
        self.assertEqual(store.value, self.command())

    def test_enable_never_overwrites_an_entry_that_is_not_ours(self):
        store = MemoryStore('C:\\Tools\\other.exe --quiet')
        with self.assertRaises(autostart.AutostartError):
            autostart.enable(self.root, store, python=self.python)
        self.assertEqual(store.value, 'C:\\Tools\\other.exe --quiet'); self.assertEqual(store.writes, [])

    def test_disable_removes_only_this_installations_entry(self):
        store = MemoryStore(self.command()); autostart.disable(self.root, store)
        self.assertIsNone(store.value)
        for kept in (self.command(self.other), 'C:\\Tools\\other.exe --quiet'):
            store = MemoryStore(kept); autostart.disable(self.root, store)
            self.assertEqual(store.value, kept)

    def test_disable_with_nothing_registered_is_a_no_op(self):
        autostart.disable(self.root, MemoryStore())

    def test_apply_follows_the_requested_state(self):
        store = MemoryStore()
        with patch.object(autostart, 'RunKey', return_value=store), patch.object(autostart, 'supported', return_value=True):
            autostart.apply(self.root, True, python=self.python); self.assertEqual(store.value, self.command())
            autostart.apply(self.root, False); self.assertIsNone(store.value)

    def test_other_platforms_cannot_enable_but_can_always_turn_it_off(self):
        with patch.object(autostart, 'supported', return_value=False):
            with self.assertRaises(autostart.AutostartError):
                autostart.apply(self.root, True)
            autostart.apply(self.root, False)


class SettingsIntegrationTests(AutostartTestCase):
    def setUp(self):
        super().setUp()
        control.save_config(dict(host.DEFAULT_CONFIG, board='guition-p4', providers=['gemini']), self.root)
        self.store = MemoryStore()
        patcher = patch.object(autostart, 'RunKey', return_value=self.store); patcher.start(); self.addCleanup(patcher.stop)
        patcher = patch.object(autostart, 'supported', return_value=True); patcher.start(); self.addCleanup(patcher.stop)
        patcher = patch.object(autostart.sys, 'executable', str(self.python)); patcher.start(); self.addCleanup(patcher.stop)

    def save(self, **options):
        return desktop.save_settings(self.root, 'guition-p4', ['gemini'], 'COM6', 60, options=options)

    def test_the_flag_is_a_validated_boolean_that_defaults_to_off(self):
        self.assertIs(FLAGS['start_host_at_login'], False)
        with self.assertRaises(ValueError):
            validate_options(dict(host.DEFAULT_CONFIG, start_host_at_login='yes'))

    def test_saving_the_flag_registers_and_removes_the_startup_entry(self):
        self.assertTrue(self.save(start_host_at_login=True)['start_host_at_login'])
        self.assertEqual(autostart.state(self.root, self.store), 'on')
        self.save(start_host_at_login=False)
        self.assertEqual(autostart.state(self.root, self.store), 'off')

    def test_a_refused_entry_saves_nothing(self):
        self.store.value = 'C:\\Tools\\other.exe --quiet'
        before = (self.root / 'tools/aim_host.json').read_bytes()
        with self.assertRaises(control.SetupError):
            self.save(start_host_at_login=True)
        self.assertEqual((self.root / 'tools/aim_host.json').read_bytes(), before)
        self.assertEqual(self.store.value, 'C:\\Tools\\other.exe --quiet')

    def test_saving_without_the_flag_leaves_a_foreign_entry_alone(self):
        self.store.value = 'C:\\Tools\\other.exe --quiet'
        self.save(reconnect_s=10)
        self.assertEqual(self.store.value, 'C:\\Tools\\other.exe --quiet')


@unittest.skipUnless(os.name == 'nt', 'Windows registry')
class RealRunKeyTests(AutostartTestCase):
    """The winreg code itself, against the real current-user key under a throwaway value name."""
    def setUp(self):
        super().setUp()
        patcher = patch.object(autostart, 'VALUE_NAME', 'LimitBuddyTest-' + uuid.uuid4().hex)
        patcher.start(); self.addCleanup(patcher.stop)
        self.store = autostart.RunKey()
        self.addCleanup(self.store.delete)   # runs first, while the throwaway name is still patched in

    def test_enable_read_state_and_disable_round_trip(self):
        self.assertIsNone(self.store.read())
        autostart.enable(self.root, self.store, python=self.python)
        self.assertEqual(self.store.read(), self.command())
        self.assertEqual(autostart.state(self.root, self.store), 'on')
        autostart.disable(self.root, self.store)
        self.assertIsNone(self.store.read())

    def test_deleting_a_missing_value_is_not_an_error(self):
        self.store.delete()

    def test_an_entry_of_another_type_is_treated_as_not_ours(self):
        import winreg
        with winreg.CreateKey(winreg.HKEY_CURRENT_USER, autostart.RUN_KEY) as key:
            winreg.SetValueEx(key, autostart.VALUE_NAME, 0, winreg.REG_DWORD, 1)
        self.assertEqual(autostart.state(self.root, self.store), 'foreign')
        with self.assertRaises(autostart.AutostartError):
            autostart.enable(self.root, self.store, python=self.python)


@unittest.skipUnless(os.name == 'nt', 'Windows registry and PowerShell')
class UninstallScriptTests(unittest.TestCase):
    """Install-LimitBuddy.ps1 -Uninstall removes a Run value pointing into its own folder, nothing else."""
    def setUp(self):
        import winreg
        self.winreg = winreg
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        # autostart writes resolved paths and PowerShell expands 8.3 short names, so compare long forms.
        self.root = Path(self.temp.name).resolve() / 'package'; self.root.mkdir()
        self.script = self.root / 'Install-LimitBuddy.ps1'
        self.script.write_bytes((ROOT / 'Install-LimitBuddy.ps1').read_bytes())
        (self.root / 'AI-Monitor-Terminal.bat').write_text('@echo off\n')
        self.name = 'LimitBuddyTest-' + uuid.uuid4().hex   # never the real LimitBuddy value
        self.addCleanup(self.delete_value)

    def delete_value(self):
        try:
            with self.winreg.OpenKey(self.winreg.HKEY_CURRENT_USER, autostart.RUN_KEY, 0, self.winreg.KEY_SET_VALUE) as key:
                self.winreg.DeleteValue(key, self.name)
        except FileNotFoundError:
            pass

    def read_value(self):
        try:
            with self.winreg.OpenKey(self.winreg.HKEY_CURRENT_USER, autostart.RUN_KEY) as key:
                return self.winreg.QueryValueEx(key, self.name)[0]
        except FileNotFoundError:
            return None

    def set_value(self, value):
        with self.winreg.CreateKey(self.winreg.HKEY_CURRENT_USER, autostart.RUN_KEY) as key:
            self.winreg.SetValueEx(key, self.name, 0, self.winreg.REG_SZ, value)

    def uninstall(self):
        return subprocess.run(['powershell', '-NoProfile', '-ExecutionPolicy', 'Bypass', '-File', str(self.script),
            '-CommandDirectory', str(self.root / 'bin'), '-EnvironmentScope', 'Process', '-RunValueName', self.name, '-Uninstall'],
            capture_output=True, text=True, timeout=30)

    def test_removes_the_entry_that_points_into_the_removed_folder(self):
        self.set_value(f'"C:\\x\\pythonw.exe" "{self.root}\\tools\\aim_control.py" --start-host')
        result = self.uninstall()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIsNone(self.read_value())

    def test_keeps_an_entry_that_belongs_to_another_folder(self):
        elsewhere = f'"C:\\x\\pythonw.exe" "{self.root.parent}\\other\\tools\\aim_control.py" --start-host'
        self.set_value(elsewhere)
        result = self.uninstall()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.read_value(), elsewhere)


if __name__ == '__main__':
    unittest.main()
