"""Synthetic native desktop flows; no panel, cloud request or real credentials."""
import contextlib
import io
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
import aim_control as control
import desktop_support as desktop
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
from PySide6.QtCore import Qt
from PySide6.QtGui import QCloseEvent, QFontDatabase
from PySide6.QtWidgets import QApplication, QDialog, QLineEdit, QMessageBox
from PySide6.QtTest import QTest
from desktop_window import MonitorWindow, ConfirmFlashDialog, ActionWorker


class DesktopSettingsTests(unittest.TestCase):
    def test_transient_windows_lock_keeps_atomic_config_replacement(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            control.save_config(dict(control.host.DEFAULT_CONFIG),root)
            replace=control.os.replace
            attempts=[]
            def transient(source,target):
                attempts.append(target)
                if len(attempts)==1:
                    error=PermissionError('synthetic sharing lock'); error.winerror=32
                    raise error
                return replace(source,target)
            with patch.object(control.os,'replace',side_effect=transient), patch.object(control.time,'sleep'):
                control.save_config(dict(control.host.DEFAULT_CONFIG,board='guition-p4',providers=['gemini']),root)
            self.assertEqual(control.local_config(root)['providers'],['gemini'])
            self.assertEqual(len(attempts),2)
            self.assertFalse(list((root/'tools').glob('*.tmp')))

    def test_preserves_existing_key_and_extra_settings(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            control.save_config(dict(control.host.DEFAULT_CONFIG, board='guition-p4',
                                     providers=['zcode'], zai_key='fixture-private-key', custom=True), root)
            config = desktop.save_settings(root, 'waveshare-s3-43', ['gemini'], 'COM7', 60)
            self.assertEqual(config['zai_key'], 'fixture-private-key')
            self.assertTrue(config['custom'])
            self.assertEqual(config['board'], 'waveshare-s3-43')
            self.assertEqual(config['providers'], ['gemini'])
            self.assertEqual(desktop.save_settings(root, 'guition-p4', ['zcode'], 'auto', 240, clear_key=True)['zai_key'], '')

    def test_invalid_settings_never_replace_existing_config(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            control.save_config(dict(control.host.DEFAULT_CONFIG, board='guition-p4', providers=['gemini']), root)
            before = (root/'tools/aim_host.json').read_bytes()
            invalid = [('bad-board', ['gemini'], 'COM6', 60, ''),
                       ('guition-p4', [], 'COM6', 60, ''),
                       ('guition-p4', ['gemini'], 'https://attacker.invalid', 60, ''),
                       ('guition-p4', ['gemini'], 'COM6', True, ''),
                       ('guition-p4', ['gemini'], 'COM6', 60, 'secret\ninvalid')]
            for args in invalid:
                with self.assertRaises(ValueError): desktop.save_settings(root, *args)
                self.assertEqual((root/'tools/aim_host.json').read_bytes(), before)

    def test_log_is_bounded_and_redacts_keys_and_control_sequences(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory); (root/'tools').mkdir()
            (root/'tools/aim_host.log').write_text('discard\n'*5000+'fixture-key\x1b[31m\nlast message\n')
            log=desktop.recent_log(root, ('fixture-key',))
            self.assertNotIn('fixture-key', log)
            self.assertNotIn('\x1b', log)
            self.assertIn('[REDACTED]', log)
            self.assertTrue(log.endswith('last message'))
            self.assertLessEqual(len(log.splitlines()), 100)

    def test_flash_revalidates_configuration_before_stopping_host(self):
        with patch.object(desktop, 'prepare_flash', return_value=('COM7', ['flasher'])), \
                patch.object(control, 'stop_host') as stop, patch.object(desktop.subprocess, 'Popen') as spawn:
            with self.assertRaises(control.SetupError):
                desktop.write_firmware(Path('.'), 'waveshare-s3-43', 'install', 'COM6', Mock())
        stop.assert_not_called(); spawn.assert_not_called()

    def test_application_update_requires_verified_panel_before_flashing(self):
        panel=Mock(); panel.heartbeat.side_effect=RuntimeError('synthetic wrong board')
        with patch.object(desktop, 'prepare_flash', return_value=('COM7', ['flasher'])), \
                patch.object(control, 'stop_host'), patch.object(control.host, 'Panel', return_value=panel), \
                patch.object(desktop.time, 'sleep'), patch.object(desktop.subprocess, 'Popen') as spawn:
            with self.assertRaises(control.SetupError):
                desktop.write_firmware(Path('.'), 'waveshare-s3-43', 'update', 'COM7', Mock())
        panel.close.assert_called_once(); spawn.assert_not_called()

    def test_console_host_is_owned_only_with_the_scoped_host_argument(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            ours=Mock(pid=123,info={'exe':str(root/'AI-Monitor-Console.exe'),'cmdline':['AI-Monitor-Console.exe','--host']})
            setup=Mock(pid=124,info={'exe':str(root/'AI-Monitor-Console.exe'),'cmdline':['AI-Monitor-Console.exe','--integrations']})
            other=Mock(pid=125,info={'exe':str(root/'other/AI-Monitor-Console.exe'),'cmdline':['AI-Monitor-Console.exe','--host']})
            with patch.object(control.psutil, 'process_iter', return_value=[ours,setup,other]):
                self.assertEqual(control.owned_hosts(root), [ours])


class DesktopWindowTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.application = QApplication.instance() or QApplication([])
        cls.application.setStyle('Fusion')
        if os.name == 'nt':
            for name in ('segoeui.ttf','segoeuib.ttf','consola.ttf'):
                QFontDatabase.addApplicationFont(str(Path(os.environ['SystemRoot'])/'Fonts'/name))

    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)
        self.window = MonitorWindow(self.root, monitor=False)
        self.window.show()
        self.application.processEvents()
        self.addCleanup(self.close_window)
        self.addCleanup(self.window.deleteLater)

    def close_window(self):
        self.window.unsaved = False
        self.window.config['keep_host_on_close'] = True
        self.window.close()

    def test_fresh_ui_has_no_selections_and_contains_nova(self):
        self.assertEqual(self.window.board.currentData(), '')
        self.assertFalse(any(box.isChecked() for box in self.window.providers.values()))
        self.assertFalse(self.window.nova.pixmap().isNull())
        self.assertFalse(self.window.windowIcon().isNull())
        self.assertTrue(self.window.activity.isReadOnly())
        self.assertTrue(self.window.host_log.isReadOnly())
        self.assertFalse((self.root/'tools/aim_host.json').exists())

    def test_missing_packaged_firmware_fails_diagnostics_without_a_crash_dialog(self):
        import aim_desktop
        with patch.object(aim_desktop.sys, 'frozen', True, create=True), \
                patch.object(aim_desktop.sys, 'argv', ['AI-Monitor.exe', '--gui-check']), \
                patch.object(control, 'ROOT', self.root), patch.object(QMessageBox, 'critical') as dialog:
            self.assertEqual(aim_desktop.main(), 1)
        dialog.assert_not_called()

    def test_flashing_diagnostics_reject_missing_package_without_launching_child(self):
        with patch.object(desktop.subprocess, 'run') as child:
            self.assertFalse(desktop.check_flasher_runtime(self.root))
        child.assert_not_called()

    def test_s3_selection_and_save_use_real_widgets(self):
        self.window.board.setCurrentIndex(self.window.board.findData('waveshare-s3-43'))
        self.window.providers['gemini'].setChecked(True)
        self.window.port.setCurrentText('COM7')
        QTest.mouseClick(self.window.save_button, Qt.MouseButton.LeftButton)
        config=control.local_config(self.root)
        self.assertEqual(config['board'],'waveshare-s3-43')
        self.assertEqual(config['providers'],['gemini'])
        self.assertEqual(config['port'],'COM7')
        self.assertFalse(self.window.unsaved)
        self.assertIn('EXPERIMENTAL',self.window.board_help.text())

    def test_host_preferences_save_and_reload_without_exposing_a_key(self):
        self.window.board.setCurrentIndex(self.window.board.findData('guition-p4'))
        self.window.providers['gemini'].setChecked(True)
        self.window.reconnect.setValue(12); self.window.token_poll.setValue(8)
        self.window.log_size.setValue(14); self.window.keep_host.setChecked(False)
        self.window.auto_start.setChecked(True); self.window.save()
        config = desktop.load_settings(self.root)
        self.assertEqual(config['reconnect_s'], 12); self.assertEqual(config['token_poll_s'], 8)
        self.assertTrue(config['start_host_on_open']); self.assertFalse(config['keep_host_on_close'])
        self.assertEqual(self.window.activity.font().pointSize(), 14)
        self.window.config['keep_host_on_close'] = True
        with patch.object(control, 'start_host') as start:
            other = MonitorWindow(self.root, monitor=False)
            self.assertEqual(other.reconnect.value(), 12)
            start.assert_not_called()
            other.config['keep_host_on_close'] = True; other.close(); other.deleteLater()

    def test_rescan_preserves_explicit_selection_and_does_not_mark_saved_setup_dirty(self):
        self.window.port.setCurrentText('COM6'); self.window.unsaved = False
        with patch.object(control.list_ports, 'comports', return_value=[Mock(device='COM4', description='Other ESP32')]):
            self.window.rescan()
        self.assertEqual(self.window.port.currentText(), 'COM6'); self.assertFalse(self.window.unsaved)
        self.assertIn('COM4', self.window.usb_help.text())
        self.assertIn('explicitly', self.window.usb_help.text())

    def test_guided_setup_routes_missing_choices_and_blocks_start_until_saved(self):
        self.assertFalse(self.window.start_button.isEnabled())
        self.assertIn('USB: choose board first', self.window.setup_progress.text())
        self.window.port.setCurrentText('COM9999')
        self.window.board.setCurrentIndex(self.window.board.findData('guition-p4'))
        self.window.continue_setup()
        self.assertEqual(self.window.tabs.currentIndex(),1)
        self.window.providers['gemini'].setChecked(True)
        self.assertFalse(self.window.start_button.isEnabled())
        self.window.continue_setup()
        self.assertFalse(self.window.unsaved); self.assertTrue(self.window.start_button.isEnabled())
        self.assertIn('saved',self.window.setup_progress.text())

    def test_ambiguous_usb_is_shown_before_starting_or_flashing(self):
        self.window.board.setCurrentIndex(self.window.board.findData('guition-p4'))
        self.window.providers['gemini'].setChecked(True); self.window.save()
        with patch.object(control.list_ports,'comports',return_value=[
                Mock(device='COM4',description='Other ESP32',vid=0x303a),
                Mock(device='COM6',description='Display',vid=0x303a)]):
            self.window.rescan()
        self.assertFalse(self.window.start_button.isEnabled())
        self.assertIn('USB port',self.window.setup_next.text())
        self.window.port.setCurrentText('COM6'); self.window.save()
        self.assertTrue(self.window.start_button.isEnabled())

    def test_failed_identity_check_guides_to_firmware_without_writing(self):
        self.window.port.setCurrentText('COM9999')
        self.window.board.setCurrentIndex(self.window.board.findData('guition-p4'))
        self.window.providers['gemini'].setChecked(True); self.window.save()
        self.window.current_action='Checking USB identity'
        with patch.object(QMessageBox,'warning'),patch.object(desktop,'write_firmware') as write, \
                patch.object(self.window,'refresh_status'):
            self.window._finished(False,'Display did not respond')
            self.window.continue_setup()
        self.assertEqual(self.window.tabs.currentIndex(),3); write.assert_not_called()

    def test_automatic_start_reuses_existing_host_without_restart(self):
        self.window.host_running = True
        with patch.object(self.window,'refresh_status'), patch.object(self.window,'start') as start:
            self.window._auto_start_if_needed()
        start.assert_not_called()

    def test_running_host_without_usb_health_routes_to_status_not_a_serial_probe(self):
        self.window.port.setCurrentText('COM9999')
        self.window.board.setCurrentIndex(self.window.board.findData('guition-p4'))
        self.window.providers['gemini'].setChecked(True); self.window.save()
        self.window.token_reporter = Mock(last_use=None)
        self.window.token_reporter.poll.return_value = None
        with patch.object(control, 'owned_hosts', return_value=[Mock(pid=1234)]), \
                patch('desktop_window.read_status', return_value=None), \
                patch.object(desktop, 'check_connection') as probe, \
                patch.object(self.window, 'start') as start:
            self.window.refresh_status()
            self.assertFalse(self.window.live_connected)
            self.assertIn('Host running:', self.window.setup_next.text())
            self.assertEqual(self.window.start_button.text(), 'Restart host')
            self.window.continue_setup()
        self.assertEqual(self.window.tabs.currentIndex(), 2)
        probe.assert_not_called(); start.assert_not_called()
        with patch.object(control, 'owned_hosts', return_value=[]):
            self.window.refresh_status()
        self.assertEqual(self.window.start_button.text(), 'Start host')
        self.assertIn('check the display connection', self.window.setup_next.text())

    def test_claude_link_controls_require_saved_selection_and_confirmation(self):
        self.assertTrue(self.window.claude_link_button.isHidden())
        self.window.board.setCurrentIndex(self.window.board.findData('guition-p4'))
        self.window.providers['claude'].setChecked(True)
        self.assertFalse(self.window.claude_link_button.isHidden())
        self.window.save()
        with patch.object(QMessageBox, 'question', return_value=QMessageBox.StandardButton.No), \
             patch.object(self.window, '_run') as run:
            self.window.claude_quota(False)
        run.assert_not_called()
        with patch.object(QMessageBox, 'question', return_value=QMessageBox.StandardButton.Yes), \
             patch.object(self.window, '_run') as run, patch('provider_setup.claude_bridge', return_value='linked') as bridge:
            self.window.claude_quota(False)
            run.call_args.args[1](Mock())
        bridge.assert_called_once_with(self.root, remove=False)

    def test_invalid_config_opens_recovery_ui_without_overwriting_file(self):
        self.window.close()
        (self.root/'tools').mkdir(exist_ok=True)
        file = self.root/'tools/aim_host.json'; file.write_text('{broken')
        other = MonitorWindow(self.root, monitor=False)
        self.assertTrue(other.config_error); self.assertFalse(other.recover_button.isHidden())
        self.assertEqual(file.read_text(), '{broken')
        with patch.object(QMessageBox, 'warning'), patch.object(desktop, 'save_settings') as save:
            other.save()
        save.assert_not_called(); other.close(); other.deleteLater()

    def test_close_can_keep_unsaved_form_and_opt_in_to_stop_host(self):
        self.window.unsaved = True
        with patch.object(QMessageBox, 'question', return_value=QMessageBox.StandardButton.No):
            event=QCloseEvent(); self.window.closeEvent(event); self.assertFalse(event.isAccepted())
        self.window.unsaved = False; self.window.config['keep_host_on_close'] = False
        with patch.object(self.window, '_run') as run:
            event=QCloseEvent(); self.window.closeEvent(event); self.assertFalse(event.isAccepted())
        self.assertTrue(self.window.close_after_stop); self.assertEqual(run.call_args.args[0], 'Stopping host')
        self.window.close_after_stop = False

    def test_existing_key_is_not_loaded_into_the_visible_password_field(self):
        self.window.close()
        control.save_config(dict(control.host.DEFAULT_CONFIG,board='guition-p4',providers=['zcode'],zai_key='fixture-private-key'),self.root)
        window=MonitorWindow(self.root,monitor=False)
        self.addCleanup(window.close)
        self.assertEqual(window.key.text(),'')
        self.assertEqual(window.key.echoMode(),QLineEdit.EchoMode.Password)
        window.append_output('never expose fixture-private-key')
        self.assertNotIn('fixture-private-key',window.activity.toPlainText())

    def test_unsaved_selection_cannot_start_a_host(self):
        with patch.object(control,'start_host') as start, patch.object(QMessageBox,'warning'):
            self.window.start()
        start.assert_not_called()

    def test_each_provider_has_visible_setup_instructions(self):
        self.window.tabs.setCurrentIndex(1)
        from provider_catalog import PROVIDER_SETUP, PROVIDERS
        self.assertEqual(set(PROVIDER_SETUP), set(PROVIDERS))
        for key in PROVIDERS:
            self.window.providers[key].setChecked(True)
            self.assertEqual(self.window.provider_guide.currentData(), key)
            self.assertIn('1.', self.window.provider_instructions.text())
            self.assertIn('2.', self.window.provider_instructions.text())
            self.assertTrue(self.window.provider_link.isEnabled())
        self.window.provider_guide.setCurrentIndex(self.window.provider_guide.findData('zcode'))
        self.assertIn('API key', self.window.provider_instructions.text())
        self.assertTrue(self.window.key_row.isVisible())
        self.window.providers['zcode'].setChecked(False)
        self.assertFalse(self.window.key_row.isVisible())

    def test_flash_starts_host_only_after_success_and_keeps_log_visible(self):
        self.window.board.setCurrentIndex(self.window.board.findData('guition-p4'))
        self.window.providers['gemini'].setChecked(True); self.window.save()
        operation=Mock(); operation.exec.return_value=QDialog.DialogCode.Accepted
        operation.kind.currentData.return_value='update'; operation.start_after.isChecked.return_value=True
        confirm=Mock(); confirm.exec.return_value=QDialog.DialogCode.Accepted; confirm.confirm.text.return_value='FLASH'
        with patch('desktop_window.FirmwareDialog', return_value=operation), \
                patch('desktop_window.ConfirmFlashDialog', return_value=confirm), \
                patch.object(desktop, 'prepare_flash', return_value=('COM7', ['tool'])), \
                patch.object(desktop, 'write_firmware') as write, patch.object(control, 'start_host') as start, \
                patch.object(self.window, '_run') as action:
            self.window.flash()
            self.assertEqual(action.call_args.args[0], 'Verifying firmware')
            action.call_args.args[1](Mock())
            write.assert_not_called(); start.assert_not_called()
            self.window.current_action = 'Verifying firmware'
            self.window._finished(True, 'Verifying firmware complete.')
            self.assertEqual(action.call_args.args[0], 'Writing firmware')
            callback=action.call_args.args[1]; emit=Mock(); callback(emit)
            write.assert_called_once(); start.assert_called_once_with(self.root, emit=emit)
            write.side_effect=control.SetupError('synthetic USB failure'); start.reset_mock()
            with self.assertRaises(control.SetupError): callback(Mock())
            start.assert_not_called()

    def test_flash_confirmation_requires_exact_text(self):
        dialog=ConfirmFlashDialog('waveshare-s3-43','COM7','install')
        self.addCleanup(dialog.deleteLater)
        self.assertFalse(dialog.write.isEnabled())
        dialog.confirm.setText('flash'); self.assertFalse(dialog.write.isEnabled())
        dialog.confirm.setText('FLASH'); self.assertTrue(dialog.write.isEnabled())

    def test_cancelled_firmware_leaves_host_and_usb_untouched(self):
        self.window.board.setCurrentIndex(self.window.board.findData('guition-p4'))
        self.window.providers['gemini'].setChecked(True)
        self.window.save()
        operation=Mock(); operation.exec.return_value=QDialog.DialogCode.Rejected
        with patch('desktop_window.FirmwareDialog',return_value=operation), \
                patch.object(desktop,'prepare_flash') as prepare, patch.object(control,'stop_host') as stop:
            self.window.flash()
        prepare.assert_not_called(); stop.assert_not_called()

    def test_closing_window_keeps_host_but_waits_for_running_actions(self):
        with patch.object(control,'stop_host') as stop:
            event=QCloseEvent(); self.window.closeEvent(event); self.assertTrue(event.isAccepted())
            self.window.busy=True
            event=QCloseEvent(); self.window.closeEvent(event); self.assertFalse(event.isAccepted())
            self.window.busy=False
        stop.assert_not_called()

    def test_worker_never_forwards_credential_exception_details(self):
        def fail(emit): raise ValueError('fixture-secret-key')
        worker=ActionWorker(fail,'Starting host'); result=[]
        worker.signals.finished.connect(lambda success,message: result.append((success,message)))
        worker.run()
        self.assertFalse(result[0][0])
        self.assertNotIn('fixture-secret-key',result[0][1])


if __name__ == '__main__': unittest.main()
