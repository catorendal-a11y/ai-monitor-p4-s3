"""Tray transitions preserve settings and the independent host; no real accounts."""
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import Mock, patch

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'tools'))
from PySide6.QtGui import QCloseEvent
from PySide6.QtCore import Qt
from PySide6.QtTest import QTest
from PySide6.QtNetwork import QLocalSocket
from PySide6.QtWidgets import QApplication, QMessageBox, QSystemTrayIcon
from desktop_window import MonitorWindow
import aim_control as control
import desktop_window as ui
from desktop_instance import DesktopInstance


class TrayTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls): cls.application = QApplication.instance() or QApplication([])

    def setUp(self):
        self.directory = tempfile.TemporaryDirectory(); self.addCleanup(self.directory.cleanup)
        self.window = MonitorWindow(Path(self.directory.name), monitor=False)
        self.window.show(); self.application.processEvents()
        self.window.tray = Mock(); self.window.tray.isVisible.return_value = True
        self.window.tray_start = Mock(); self.window.tray_stop = Mock(); self.window.tray_quit = Mock()
        available = patch.object(QSystemTrayIcon, 'isSystemTrayAvailable', return_value=True)
        available.start(); self.addCleanup(available.stop)
        hosts = patch.object(control, 'owned_hosts', return_value=[])
        hosts.start(); self.addCleanup(hosts.stop)
        self.addCleanup(self.cleanup_window)

    def cleanup_window(self):
        self.window.unsaved=False; self.window.quit_requested=True
        self.window.config['keep_host_on_close']=True
        self.window.close(); self.window.deleteLater()

    def test_minimize_preserves_unsaved_key_and_never_stops_host(self):
        self.window.key.setText('fixture-key'); self.window.unsaved=True
        with patch.object(control, 'stop_host') as stop:
            self.window.showMinimized(); self.application.processEvents(); self.application.processEvents()
        self.assertTrue(self.window.hidden_to_tray); self.assertFalse(self.window.isVisible())
        self.assertTrue(self.window.unsaved); self.assertEqual(self.window.key.text(), 'fixture-key')
        stop.assert_not_called()
        self.window.restore_from_tray()
        self.assertTrue(self.window.isVisible()); self.assertFalse(self.window.isMinimized())

    def test_close_to_tray_retains_unsaved_settings_without_a_quit_dialog(self):
        self.window.config['close_to_tray']=True; self.window.unsaved=True
        self.window.config['keep_host_on_close']=False
        with patch.object(QMessageBox,'question') as question, patch.object(control,'stop_host') as stop:
            event=QCloseEvent(); self.window.closeEvent(event)
        self.assertFalse(event.isAccepted()); self.assertTrue(self.window.hidden_to_tray)
        self.assertTrue(self.window.unsaved); question.assert_not_called(); stop.assert_not_called()

    def test_no_tray_leaves_normal_close_behavior_available(self):
        self.window.config['close_to_tray']=True
        with patch.object(QSystemTrayIcon,'isSystemTrayAvailable',return_value=False):
            self.assertFalse(self.window.hide_to_tray())
            event=QCloseEvent(); self.window.closeEvent(event)
        self.assertTrue(event.isAccepted())

    def test_quit_uses_stop_preference_instead_of_hiding(self):
        self.window.config.update(close_to_tray=True, keep_host_on_close=False)
        with patch.object(self.window,'_run') as run:
            self.window.request_quit()
        self.assertTrue(self.window.quit_requested); self.assertTrue(self.window.close_after_stop)
        self.assertEqual(run.call_args.args[0], 'Stopping host')
        self.window.close_after_stop=False

    def test_declined_unsaved_quit_resets_exit_intent(self):
        self.window.config['close_to_tray']=True; self.window.unsaved=True
        with patch.object(QMessageBox,'question',return_value=QMessageBox.StandardButton.No):
            self.window.request_quit()
        self.assertFalse(self.window.quit_requested); self.assertTrue(self.window.isVisible())
        self.assertTrue(self.window.unsaved)

    def test_busy_quit_restores_progress_instead_of_exiting(self):
        self.window.hide_to_tray(); self.window.busy=True
        self.window.request_quit()
        self.assertTrue(self.window.isVisible()); self.assertFalse(self.window.quit_requested)
        self.assertTrue(self.window.busy)
        self.window.busy=False

    def test_hidden_action_error_reopens_the_window(self):
        self.window.hide_to_tray()
        with patch.object(QMessageBox,'warning') as warning:
            self.window._finished(False, 'Synthetic USB failure')
        self.assertTrue(self.window.isVisible()); warning.assert_called_once()

    def test_tray_tooltip_and_quit_menu_contain_no_saved_key(self):
        self.window.config['zai_key']='fixture-private-key'
        self.window.config['keep_host_on_close']=False
        self.window.refresh_tray()
        self.assertNotIn('fixture-private-key',str(self.window.tray.setToolTip.call_args))
        self.assertIn('stop host',self.window.tray_quit.setText.call_args.args[0])

    def test_tray_preferences_are_saved_and_reloaded(self):
        self.window.board.setCurrentIndex(self.window.board.findData('guition-p4'))
        self.window.providers['gemini'].setChecked(True)
        self.window.minimize_tray.setChecked(False); self.window.close_tray.setChecked(True)
        self.window.save()
        config=control.local_config(self.window.root)
        self.assertFalse(config['minimize_to_tray']); self.assertTrue(config['close_to_tray'])
        other=MonitorWindow(self.window.root,monitor=False)
        self.assertFalse(other.minimize_tray.isChecked()); self.assertTrue(other.close_tray.isChecked())
        other.quit_requested=True; other.close(); other.deleteLater()

    def test_restoring_retains_window_size_and_maximized_state(self):
        self.window.resize(1200, 900); self.application.processEvents()
        before=self.window.size()
        self.window.showMinimized(); self.application.processEvents(); self.application.processEvents()
        self.window.restore_from_tray(); self.application.processEvents()
        self.assertEqual(self.window.size(),before)
        self.window.showMaximized(); self.application.processEvents()
        self.window.hide_to_tray(); self.window.restore_from_tray()
        self.assertTrue(self.window.isMaximized())

    def test_twelve_minimize_restore_cycles_reuse_the_same_window_icon_and_edits(self):
        window = self.window
        window.key.setText('synthetic-unsaved-key')
        window.unsaved = True
        before = window.size(); icon = window.tray
        with patch.object(control, 'start_host') as start, patch.object(control, 'stop_host') as stop:
            for cycle in range(12):
                with self.subTest(cycle=cycle):
                    window.showMinimized(); QTest.qWait(5)
                    self.assertTrue(window.hidden_to_tray)
                    self.assertFalse(window.isVisible())
                    if cycle % 3 == 0: window._tray_activated(QSystemTrayIcon.ActivationReason.Trigger)
                    elif cycle % 3 == 1: window._tray_activated(QSystemTrayIcon.ActivationReason.DoubleClick)
                    else: window.activate_requested('show')
                    QTest.qWait(5)
                    self.assertTrue(window.isVisible()); self.assertFalse(window.isMinimized())
                    self.assertFalse(window.hidden_to_tray); self.assertIs(window.tray, icon)
                    self.assertEqual(window.size(), before)
                    self.assertEqual(window.key.text(), 'synthetic-unsaved-key')
                    self.assertTrue(window.unsaved); self.assertFalse(window.closed)
        start.assert_not_called(); stop.assert_not_called()

    def test_twelve_maximized_cycles_and_duplicate_hide_preserve_restore_state(self):
        window = self.window
        window.showMaximized(); QTest.qWait(5)
        for cycle in range(12):
            with self.subTest(cycle=cycle):
                window.showMinimized(); QTest.qWait(5)
                self.assertTrue(window.hidden_to_tray)
                saved = bytes(window.restore_geometry)
                epoch = window.status_epoch
                window.hide_to_tray()
                self.assertEqual(bytes(window.restore_geometry), saved)
                self.assertEqual(window.status_epoch, epoch)
                window.activate_requested('firmware' if cycle % 2 else 'show')
                QTest.qWait(5)
                self.assertTrue(window.isVisible()); self.assertTrue(window.isMaximized())
                self.assertFalse(window.isMinimized()); self.assertFalse(window.hidden_to_tray)
        self.assertEqual(window.tabs.currentIndex(), 3)

    def test_restore_cancels_old_hide_callbacks_and_clears_minimized_saved_geometry(self):
        window = self.window
        window.showMinimized()
        old_generation = window.visibility_generation
        window.restore_from_tray()
        self.application.processEvents()
        window._hide_minimized(old_generation)
        self.assertTrue(window.isVisible()); self.assertFalse(window.hidden_to_tray)
        window.hide_to_tray()
        # Windows may restore the minimized bit encoded in saved geometry.
        # Use real Qt state changes; the restore must force a visible state.
        def minimized_geometry(_geometry):
            window.showMinimized()
            return True
        with patch.object(window, 'restoreGeometry', side_effect=minimized_geometry):
            window.restore_from_tray(); QTest.qWait(10)
        self.assertTrue(window.isVisible()); self.assertFalse(window.isMinimized())
        self.assertFalse(window.hidden_to_tray)

    def test_missing_tray_icon_or_shell_restores_window_and_taskbar_fallback(self):
        window = self.window
        for lost_shell in (False, True):
            with self.subTest(lost_shell=lost_shell):
                window.tray.isVisible.return_value = True
                window.hide_to_tray()
                window.tray.isVisible.return_value = False
                with patch.object(QSystemTrayIcon, 'isSystemTrayAvailable', return_value=not lost_shell):
                    window.refresh_tray()
                self.assertTrue(window.isVisible()); self.assertFalse(window.isMinimized())
                self.assertFalse(window.hidden_to_tray)
                self.assertIn('desktop shortcut', window.notice.text())
        window.tray.isVisible.return_value = True
        with patch.object(QSystemTrayIcon, 'isSystemTrayAvailable', return_value=False):
            window.showMinimized(); QTest.qWait(5)
            self.assertTrue(window.isVisible()); self.assertTrue(window.isMinimized())
            self.assertFalse(window.hidden_to_tray)
            window.activate_requested(); QTest.qWait(5)
        self.assertTrue(window.isVisible()); self.assertFalse(window.isMinimized())

    def test_tray_creation_reuses_icon_and_menu_without_duplicate_activation_slots(self):
        window = self.window
        window.tray = None
        icon = Mock()
        with patch.object(ui, 'QSystemTrayIcon', return_value=icon) as construct:
            window._create_tray()
            menu = window.tray_menu
            for _ in range(12): window._create_tray()
        construct.assert_called_once()
        self.assertIs(window.tray, icon); self.assertIs(window.tray_menu, menu)
        icon.activated.connect.assert_called_once()
        self.assertEqual(len(menu.actions()), 6)
        window.tray_timer.stop()

    def test_shortcut_reopen_preserves_first_install_choices_without_preselecting_an_ai(self):
        window = self.window
        self.assertEqual(window.board.currentData(), '')
        self.assertFalse(any(box.isChecked() for box in window.providers.values()))
        self.assertFalse(window.start_button.isEnabled()); self.assertFalse(window.enter_key_button.isEnabled())
        window.board.setCurrentIndex(window.board.findData('waveshare-s3-43'))
        window.providers['zcode'].setChecked(True)
        window.key.setText('synthetic-new-user-key')
        window.hide_to_tray(); window.activate_requested('show'); QTest.qWait(5)
        self.assertEqual(window.board.currentData(), 'waveshare-s3-43')
        self.assertTrue(window.providers['zcode'].isChecked())
        self.assertEqual(window.key.text(), 'synthetic-new-user-key')
        self.assertTrue(window.enter_key_button.isEnabled())
        self.assertFalse(window.start_button.isEnabled())
        self.assertFalse((window.root/'tools/aim_host.json').exists())

    def test_twelve_real_local_shortcut_requests_restore_hidden_window_and_requested_page(self):
        window = self.window
        owner = DesktopInstance(window.root)
        self.assertTrue(owner.claim()); self.addCleanup(owner.close)
        owner.requested.connect(window.activate_requested)
        for cycle in range(12):
            with self.subTest(cycle=cycle):
                window.showMinimized(); QTest.qWait(5)
                self.assertTrue(window.hidden_to_tray)
                socket = QLocalSocket(); socket.connectToServer(owner.name)
                self.assertTrue(socket.waitForConnected(1000))
                socket.write(b'firmware\n' if cycle % 2 else b'show\n')
                socket.flush(); QTest.qWait(20)
                socket.abort(); QTest.qWait(5)
                self.assertTrue(window.isVisible()); self.assertFalse(window.isMinimized())
                self.assertFalse(window.hidden_to_tray); self.assertTrue(owner.lock.isLocked())
        self.assertEqual(window.tabs.currentIndex(), 3)

    def test_desktop_application_does_not_exit_when_only_window_is_hidden(self):
        previous = self.application.quitOnLastWindowClosed()
        self.addCleanup(self.application.setQuitOnLastWindowClosed, previous)
        instance = Mock(); instance.claim.return_value = True
        window = Mock()
        with patch('desktop_instance.DesktopInstance', return_value=instance), \
                patch.object(ui, 'MonitorWindow', return_value=window), \
                patch.object(self.application, 'exec', return_value=0):
            self.assertEqual(ui.run_desktop(), 0)
        self.assertFalse(self.application.quitOnLastWindowClosed())
        instance.requested.connect.assert_called_once_with(window.activate_requested)
        instance.close.assert_called_once()


if __name__=='__main__': unittest.main()
