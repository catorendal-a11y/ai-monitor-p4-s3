"""Double-click handling never writes USB firmware; CLI remains upstream esptool."""
import ctypes
import importlib.util
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch

spec = importlib.util.spec_from_file_location('flasher_entry', Path(__file__).resolve().parents[1]/'scripts/esptool_entry.py')
entry = importlib.util.module_from_spec(spec)
spec.loader.exec_module(entry)


class FlasherEntryTests(unittest.TestCase):
    def test_missing_app_explains_complete_package_without_launching(self):
        with tempfile.TemporaryDirectory() as directory, patch.object(ctypes, 'windll', Mock(), create=True) as api, \
                patch.object(entry.subprocess, 'Popen') as launch:
            self.assertEqual(entry.open_firmware_ui(Path(directory)), 1)
            self.assertIn('complete', api.user32.MessageBoxW.call_args.args[1])
            launch.assert_not_called()

    def test_double_click_requires_choice_and_opens_firmware_tab_without_writing(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory); (root/'AI-Monitor.exe').touch()
            with patch.object(ctypes, 'windll', Mock(), create=True) as api, \
                    patch.object(entry.subprocess, 'Popen') as launch, \
                    patch.object(entry.subprocess, 'CREATE_NO_WINDOW', 0, create=True):
                api.user32.MessageBoxW.return_value=7
                self.assertEqual(entry.open_firmware_ui(root), 0); launch.assert_not_called()
                api.user32.MessageBoxW.return_value=6
                self.assertEqual(entry.open_firmware_ui(root), 0)
                self.assertEqual(launch.call_args.args[0], [str(root/'AI-Monitor.exe'), '--firmware'])
                self.assertEqual(launch.call_args.kwargs['env']['PYINSTALLER_RESET_ENVIRONMENT'], '1')

    def test_cli_arguments_are_passed_to_upstream(self):
        with patch.object(entry.sys, 'argv', ['firmware-flasher', '--help']), patch.dict('sys.modules', esptool=Mock()) as modules:
            self.assertEqual(entry.main(), 0)
            modules['esptool']._main.assert_called_once_with()


if __name__ == '__main__': unittest.main()
