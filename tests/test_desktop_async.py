"""Real Qt workers with delayed synthetic I/O and child processes; no AI or USB."""
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from unittest.mock import Mock, patch

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'tools'))
from PySide6.QtCore import QTimer, QThread, Slot
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QMessageBox
import desktop_support as desktop
import desktop_window as ui


class ObservedWindow(ui.MonitorWindow):
    def __init__(self, *args, **kwargs):
        self.callback_threads = []
        super().__init__(*args, **kwargs)

    @Slot(bool, str)
    def _finished(self, success, message):
        self.callback_threads.append(QThread.currentThread())
        super()._finished(success, message)

    @Slot(object)
    def _status_finished(self, result):
        self.callback_threads.append(QThread.currentThread())
        super()._status_finished(result)

    @Slot(object)
    def _scanned(self, result):
        self.callback_threads.append(QThread.currentThread())
        super()._scanned(result)


class BackgroundFlowTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.application = QApplication.instance() or QApplication([])

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        with patch.object(ui.control.list_ports, 'comports', return_value=[]):
            self.window = ObservedWindow(self.root, monitor=False)
        self.window.callback_threads = []
        warnings = patch.object(QMessageBox, 'warning')
        warnings.start(); self.addCleanup(warnings.stop)
        self.window.monitor_enabled = True
        self.window.show()
        self.application.processEvents()
        self.ticks = []
        self.timer = QTimer(); self.timer.setInterval(5)
        self.timer.timeout.connect(lambda: self.ticks.append(time.monotonic()))
        self.timer.start()

    def tearDown(self):
        self.timer.stop()
        self.window.monitor_enabled = False
        self.window.closed = True
        for pool in (self.window.pool, self.window.status_pool, self.window.scan_pool):
            self.assertTrue(pool.waitForDone(3000), 'A worker was left running')
        self.application.processEvents()  # Drain queued results before destroying their receiver.
        self.assertTrue(all(thread == self.application.thread() for thread in self.window.callback_threads))
        self.window.unsaved = False
        self.window.config['keep_host_on_close'] = True
        self.window.close(); self.window.deleteLater()
        self.application.processEvents()
        self.temp.cleanup()

    def wait_until(self, condition, seconds=3):
        deadline = time.monotonic() + seconds
        while not condition() and time.monotonic() < deadline:
            QTest.qWait(10)
            time.sleep(0.002)  # qWait can retain the Python GIL on Linux; let Python workers run.
        self.assertTrue(condition())

    @staticmethod
    def sample():
        return dict(running=True, summary='SYNTHETIC HOST RUNNING', health=None,
                    log='', sample=None, reporter=Mock(last_use=None), working=False)

    def test_slow_read_keeps_ui_live_coalesces_and_rejects_stale_results(self):
        release = threading.Event(); entered = threading.Event(); calls = []
        def slow(*args):
            calls.append(threading.get_ident()); entered.set()
            release.wait(2)
            return self.sample()
        with patch.object(ui, 'collect_status', side_effect=slow):
            self.window.refresh_status()
            self.wait_until(entered.is_set)
            try:
                for _ in range(20): self.window.refresh_status()
                QTest.qWait(80)
                self.assertGreater(len(self.ticks), 3)
                self.assertEqual(len(calls), 1)
                self.assertNotEqual(calls[0], threading.get_ident())
                self.window.status_epoch += 1  # A saved setup or tray transition.
            finally: release.set()
            self.wait_until(lambda: self.window.status_worker is None)
            self.assertFalse(self.window.host_running)
            self.window.refresh_status()
            self.wait_until(lambda: self.window.status_worker is None)
        self.assertTrue(self.window.host_running)
        self.assertEqual(len(calls), 2)

    def test_async_scan_preserves_port_edited_while_scan_is_running(self):
        release = threading.Event(); entered = threading.Event()
        def scan():
            entered.set(); release.wait(2)
            return [Mock(device='COM9998', description='Synthetic', vid=0x303a)]
        with patch.object(ui.control.list_ports, 'comports', side_effect=scan):
            self.window.rescan(); self.wait_until(entered.is_set)
            try:
                self.window.port.setCurrentText('COM9999')
                QTest.qWait(70); self.assertGreater(len(self.ticks), 3)
            finally: release.set()
            self.wait_until(lambda: self.window.scan_worker is None)
        self.assertEqual(self.window.port.currentText(), 'COM9999')
        self.assertIn('COM9998', self.window.usb_help.text())

    def test_real_hung_child_is_reaped_before_worker_releases_busy(self):
        children = []; spawn = subprocess.Popen
        def child(*args, **kwargs):
            process = spawn(*args, **kwargs); children.append(process); return process
        action = lambda emit: desktop.run_firmware_command(
            [sys.executable, '-c', 'import time; time.sleep(60)'], self.root,
            dict(os.environ), emit, timeout_s=0.25, idle_s=5)
        with patch.object(desktop.subprocess, 'Popen', side_effect=child), \
                patch.object(QMessageBox, 'warning') as warning:
            original_stdout = sys.stdout
            self.window._run('Synthetic firmware timeout', action)
            self.assertTrue(self.window.busy)
            self.wait_until(lambda: not self.window.busy)
            self.assertIs(sys.stdout, original_stdout)
            warning.assert_called_once()
        self.assertEqual(len(children), 1)
        self.assertIsNotNone(children[0].poll())
        self.assertIn('timed out', self.window.notice.text())
        self.assertTrue(self.window.callback_threads)
        self.assertGreater(len(self.ticks), 3)
        # A second real worker can finish after the timed-out child has exited.
        self.window._run('Next synthetic action', lambda emit: emit('safe to retry'))
        self.wait_until(lambda: not self.window.busy)
        self.assertIn('safe to retry', self.window.activity.toPlainText())

    def test_successful_child_output_is_delivered_and_nonzero_exit_is_rejected(self):
        output = []
        desktop.run_firmware_command([sys.executable, '-c', 'print("synthetic complete")'],
                                     self.root, dict(os.environ), output.append, timeout_s=5)
        self.assertIn('synthetic complete', output)
        with self.assertRaises(ui.control.SetupError):
            desktop.run_firmware_command([sys.executable, '-c', 'raise SystemExit(2)'],
                                         self.root, dict(os.environ), output.append, timeout_s=5)


if __name__ == '__main__': unittest.main()
