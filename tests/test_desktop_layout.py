"""Stable Qt action positions and actual press/update/release flows; synthetic I/O only."""
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import Mock, patch

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
from PySide6.QtCore import QPoint, Qt
from PySide6.QtGui import QFontDatabase, QPalette
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QMessageBox, QScrollArea
import desktop_window as ui


class DesktopLayoutTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])
        cls.app.setStyle('Fusion')
        if os.name == 'nt':
            for name in ('segoeui.ttf', 'segoeuib.ttf', 'consola.ttf'):
                QFontDatabase.addApplicationFont(str(Path(os.environ['SystemRoot']) / 'Fonts' / name))

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        with patch.object(ui.control.list_ports, 'comports', return_value=[]):
            self.window = ui.MonitorWindow(Path(self.temp.name), monitor=False)
        self.window.show()
        self.settle()

    def tearDown(self):
        self.window.busy = self.window.unsaved = False
        self.window.config['keep_host_on_close'] = True
        self.window.closed = True
        self.window.close()
        self.window.deleteLater()
        self.settle()
        self.temp.cleanup()

    def settle(self):
        for _ in range(3): self.app.processEvents()

    def geometry(self, *widgets):
        self.settle()
        return [(widget.mapTo(self.window, QPoint()).x(), widget.mapTo(self.window, QPoint()).y(),
                 widget.width(), widget.height()) for widget in widgets]

    def snapshot(self, name):
        target = os.environ.get('AIM_DESKTOP_PREVIEWS')
        if target:
            folder = Path(target); folder.mkdir(parents=True, exist_ok=True)
            self.assertTrue(self.window.grab().save(str(folder / (name + '.png'))))

    def prepared(self):
        window = self.window
        window.board.setCurrentIndex(window.board.findData('guition-p4'))
        window.providers['gemini'].setChecked(True)
        window.port.setCurrentText('COM9999')
        window.save()
        self.settle()

    def status(self, running=True, connected=True, providers=None):
        window = self.window
        return window.status_epoch, dict(
            running=running, summary='USB CONNECTED' if connected else 'HOST STOPPED',
            health=dict(state='connected' if connected else 'disconnected',
                        board=window.config['board'], port='COM9999', providers=providers or {}),
            log='Synthetic observation; no accounts or hardware were accessed.',
            sample=dict(known=True, seen=False), reporter=Mock(last_use=None), working=False)

    def test_top_actions_and_setup_positions_survive_busy_long_text_and_usb_changes(self):
        window = self.window
        for width, height in ((1200, 900), (1040, 760)):
            with self.subTest(size=(width, height)):
                window.resize(width, height)
                window.tabs.setCurrentIndex(0)
                controls = (window.save_button, window.start_button, window.stop_button,
                            window.integration_button, window.setup_next, window.board,
                            window.port, window.rescan_button, window.check_usb_button,
                            window.console_tabs, window.tabs)
                expected = self.geometry(*controls)
                window.notice.setText('Synthetic long status message. ' * 60)
                window.usb_help.setText('COM9999: synthetic long USB device description. ' * 60)
                window.setup_progress.setText('Synthetic setup progress. ' * 60)
                window.board_help.setText('Synthetic board help. ' * 60)
                window.host_state.setText('Synthetic connection summary. ' * 60)
                window.token_state.setText('Synthetic token observation. ' * 60)
                self.assertEqual(self.geometry(*controls), expected)
                with patch.object(window.pool, 'start'), patch.object(window, 'refresh_status'):
                    window._run('Synthetic busy state', lambda emit: None)
                    self.assertFalse(window.setup_next.isEnabled())
                    self.assertEqual(self.geometry(*controls), expected)
                    window._finished(True, 'Synthetic completed state. ' * 60)
                self.assertEqual(self.geometry(*controls), expected)
                self.assertGreater(window.notice.verticalScrollBar().maximum(), 0)
                if width == 1200: self.snapshot('setup-stable-long-status')

    def test_provider_guides_and_optional_actions_never_move_persistent_controls(self):
        window = self.window
        window.tabs.setCurrentIndex(1)
        scroll = window.tabs.currentWidget()
        self.assertIsInstance(scroll, QScrollArea)
        for width, height in ((1200, 900), (1040, 760)):
            window.resize(width, height)
            self.settle()
            scroll.verticalScrollBar().setValue(0)
            controls = (window.provider_guide, window.provider_instructions, window.provider_link,
                        window.provider_action_slot, window.provider_remove_slot,
                        window.key_row, window.interval, window.save_button,
                        window.read_ai_button, window.enter_key_button, window.check_ai_button)
            expected = self.geometry(*controls)
            for provider in ui.PROVIDERS:
                with self.subTest(size=(width, height), provider=provider):
                    window.providers['zcode'].setChecked(provider == 'zcode')
                    window.provider_guide.setCurrentIndex(window.provider_guide.findData(provider))
                    self.assertEqual(self.geometry(*controls), expected)
                    self.assertEqual(window.provider_instructions.text(), ui.PROVIDER_SETUP[provider][0])
                    if provider in ('codex', 'zcode', 'claude'):
                        window.read_ai_instructions()
                        self.settle(); self.snapshot('provider-' + provider + '-' + str(width))
                        guide_position = window.provider_guide.mapTo(scroll.viewport(), QPoint())
                        self.assertGreaterEqual(guide_position.y(), 0)
                        instructions_position = window.provider_instructions.mapTo(scroll.viewport(), QPoint())
                        self.assertGreaterEqual(instructions_position.y(), 0)
                        self.assertLessEqual(instructions_position.y() + window.provider_instructions.height(),
                                             scroll.viewport().height())
                        if provider == 'zcode':
                            window.enter_zai_key()
                            self.settle(); self.snapshot('provider-zcode-key-' + str(width))
                        window.read_ai_button.setFocus()
                        scroll.verticalScrollBar().setValue(0)
                        self.settle()
            window.provider_instructions.setText('Synthetic unusually long instructions. ' * 120)
            self.assertEqual(self.geometry(*controls), expected)
            self.assertGreater(window.provider_instructions.verticalScrollBar().maximum(), 0)
            window.provider_guide.setCurrentIndex(-1)
            self.assertFalse(window.provider_link.isEnabled())
            self.assertTrue(window.codex_setup_button.isHidden())
            self.assertTrue(window.claude_link_button.isHidden())

    def test_pressing_continue_keeps_its_visible_route_until_release(self):
        self.prepared()
        window = self.window
        self.assertIn('check the display connection', window.setup_next.text())
        before = self.geometry(window.setup_next, window.start_button)
        with patch.object(window, 'check_connection') as check, patch.object(window, 'start') as start:
            QTest.mousePress(window.setup_next, Qt.MouseButton.LeftButton)
            window._status_finished(self.status())
            self.assertFalse(window.host_running)
            self.assertIn('check the display connection', window.setup_next.text())
            self.assertEqual(self.geometry(window.setup_next, window.start_button), before)
            QTest.mouseRelease(window.setup_next, Qt.MouseButton.LeftButton)
            self.settle()
        check.assert_called_once(); start.assert_not_called()
        self.assertTrue(window.host_running)
        self.assertIn('Connected', window.setup_next.text())
        self.assertEqual(self.geometry(window.setup_next, window.start_button), before)

    def test_usb_scan_during_press_cannot_replace_the_pressed_action(self):
        self.prepared()
        window = self.window
        window.port.setCurrentText('auto'); window.save()
        ports = [Mock(device='COM9998', description='Synthetic one', vid=0x303a),
                 Mock(device='COM9999', description='Synthetic two', vid=0x303a)]
        with patch.object(window, 'check_connection') as check:
            QTest.mousePress(window.setup_next, Qt.MouseButton.LeftButton)
            window._scanned(ports)
            self.assertEqual(window.usb_ports, [])
            QTest.mouseRelease(window.setup_next, Qt.MouseButton.LeftButton)
            self.settle()
        check.assert_called_once()
        self.assertEqual(window.usb_ports, ports)
        self.assertIn('select the display USB port', window.setup_next.text())
        self.assertFalse(window.start_button.isEnabled())

    def test_stale_failed_read_and_deferred_result_cannot_undo_new_configuration(self):
        self.prepared()
        window = self.window
        old_epoch = window.status_epoch
        window.status_epoch += 1
        window._status_finished(self.status())
        window._status_finished((old_epoch, None))
        self.assertTrue(window.live_connected)
        with patch.object(window, 'start'):
            QTest.mousePress(window.start_button, Qt.MouseButton.LeftButton)
            window._status_finished((window.status_epoch, None))
            window.status_epoch += 1
            QTest.mouseRelease(window.start_button, Qt.MouseButton.LeftButton)
            self.settle()
        self.assertTrue(window.live_connected)

    def test_provider_actions_require_saved_selection_and_instruction_navigation_is_explicit(self):
        self.prepared()
        window = self.window
        window.tabs.setCurrentIndex(1)
        window.provider_guide.setCurrentIndex(window.provider_guide.findData('claude'))
        self.assertFalse(window.enter_key_button.isEnabled())
        self.assertFalse(window.claude_link_button.isEnabled())
        window.providers['claude'].setChecked(True)
        self.assertFalse(window.claude_link_button.isEnabled())
        window.save()
        self.assertTrue(window.claude_link_button.isEnabled())
        window.providers['zcode'].setChecked(True)
        self.assertTrue(window.enter_key_button.isEnabled())
        scroll = window.tabs.widget(1)
        scroll.verticalScrollBar().setValue(0)
        before = scroll.verticalScrollBar().value()
        window._status_finished(self.status())
        self.assertEqual(scroll.verticalScrollBar().value(), before)
        QTest.mouseClick(window.read_ai_button, Qt.MouseButton.LeftButton)
        self.settle()
        self.assertGreater(scroll.verticalScrollBar().value(), before)
        guide_position = window.provider_guide.mapTo(scroll.viewport(), QPoint())
        self.assertGreaterEqual(guide_position.y(), 0)
        instructions_position = window.provider_instructions.mapTo(scroll.viewport(), QPoint())
        self.assertGreaterEqual(instructions_position.y(), 0)
        self.assertLessEqual(instructions_position.y() + window.provider_instructions.height(), scroll.viewport().height())
        window.enter_zai_key()
        self.settle()
        key_position = window.key_row.mapTo(scroll.viewport(), QPoint())
        self.assertGreaterEqual(key_position.y(), 0)
        self.assertLessEqual(key_position.y() + window.key_row.height(), scroll.viewport().height())
    def test_host_health_count_recovery_visibility_and_all_tabs_keep_top_actions_fixed(self):
        self.prepared()
        window = self.window
        controls = (window.save_button, window.start_button, window.stop_button,
                    window.integration_button, window.console_tabs)
        expected = self.geometry(*controls)
        for tab in range(window.tabs.count()):
            window.tabs.setCurrentIndex(tab)
            self.assertEqual(self.geometry(*controls), expected)
        window.tabs.setCurrentIndex(2)
        host_controls = (window.reconnect, window.token_poll, window.log_size,
                         window.auto_start, window.keep_host, window.minimize_tray, window.close_tray)
        host_expected = self.geometry(*host_controls)
        for count in (0, 1, len(ui.PROVIDERS)):
            window.provider_health.setText('\n'.join('Synthetic provider: quota unavailable and detailed help. ' * 6
                                                    for _ in range(count)))
            window.recover_button.setVisible(count > 0)
            self.assertEqual(self.geometry(*host_controls), host_expected)
            self.assertEqual(self.geometry(*controls), expected)
        window.provider_health.setText('Gemini CLI: local token activity available; account quota not supplied.\n'
                                       'OpenCode: local token activity available; account quota not supplied.')
        window.tabs.currentWidget().ensureWidgetVisible(window.provider_health, 0, 0)
        self.settle(); self.snapshot('host-settings')
        for tab, name in ((3, 'firmware'), (4, 'help')):
            window.tabs.setCurrentIndex(tab); self.settle(); self.snapshot(name)

    def test_minimum_window_all_tabs_stay_within_the_viewport_and_can_scroll(self):
        window = self.window
        window.resize(1040, 760)
        self.settle()
        expected = self.geometry(window.save_button, window.start_button, window.stop_button,
                                 window.integration_button, window.console_tabs)
        for tab, name in enumerate(('setup', 'ai-choices', 'host-preferences', 'firmware', 'help')):
            window.tabs.setCurrentIndex(tab)
            self.settle()
            self.assertEqual(window.size().width(), 1040)
            self.assertEqual(window.size().height(), 760)
            self.assertEqual(self.geometry(window.save_button, window.start_button, window.stop_button,
                                           window.integration_button, window.console_tabs), expected)
            scroll = window.tabs.currentWidget()
            self.assertIsInstance(scroll, QScrollArea)
            self.assertEqual(scroll.horizontalScrollBar().maximum(), 0)
            self.snapshot(name + '-minimum')
            if scroll.verticalScrollBar().maximum():
                scroll.verticalScrollBar().setValue(scroll.verticalScrollBar().maximum())
                self.settle(); self.snapshot(name + '-minimum-bottom')

    def test_experimental_board_warning_keeps_amber_semantics_without_moving_controls(self):
        window = self.window
        controls = (window.board, window.check_usb_button, window.setup_next, window.save_button)
        expected = self.geometry(*controls)
        window.board.setCurrentIndex(window.board.findData('waveshare-s3-43'))
        self.settle()
        self.assertIn('EXPERIMENTAL', window.board_help.text())
        self.assertEqual(window.board_help.palette().color(QPalette.ColorRole.Text).name(), '#ffcf86')
        self.assertEqual(self.geometry(*controls), expected)
        window.board.setCurrentIndex(window.board.findData('guition-p4'))
        self.settle()
        self.assertEqual(window.board_help.palette().color(QPalette.ColorRole.Text).name(), '#b3c4cd')
        self.assertEqual(self.geometry(*controls), expected)


if __name__ == '__main__': unittest.main()
