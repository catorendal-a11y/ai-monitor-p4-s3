"""Native Qt control panel with the original NOVA artwork and a bounded log view."""
from __future__ import annotations

from datetime import datetime
import os
from pathlib import Path
import sys
import time

from PySide6.QtCore import QObject, QRunnable, QThreadPool, QTimer, Qt, Signal, Slot, QSignalBlocker, QEvent
from PySide6.QtGui import QDesktopServices, QFont, QIcon, QPixmap, QShortcut, QKeySequence
from PySide6.QtCore import QUrl
from PySide6.QtWidgets import (
    QApplication, QCheckBox, QComboBox, QDialog, QDialogButtonBox, QFrame,
    QGridLayout, QHBoxLayout, QLabel, QLineEdit, QMainWindow, QMessageBox,
    QPlainTextEdit, QProgressBar, QPushButton, QScrollArea, QSpinBox,
    QTabWidget, QVBoxLayout, QWidget, QSystemTrayIcon, QMenu, QSizePolicy, QStackedWidget,
)

import aim_control as control
import desktop_support as desktop
from board_profiles import BOARDS, get_board
from host_security import safe_text, serial_port
from provider_catalog import PROVIDERS, PROVIDER_SETUP
from host_status import read_status
from project_version import HOST_VERSION

APP_VERSION = HOST_VERSION
ASSETS = Path(getattr(sys, '_MEIPASS', Path(__file__).resolve().parents[1])) / 'assets/desktop'

STYLE = '''
QWidget { background: #101b22; color: #e8f0f2; font-family: "Segoe UI"; font-size: 14px; }
QFrame#sidebar { background: #132b28; border-right: 1px solid #294139; }
QFrame#card { background: #182831; border: 1px solid #2b414b; border-radius: 12px; }
QLabel { background: transparent; border: none; }
QLabel#muted { color: #b3c4cd; }
QLabel#eyebrow { color: #70e6ae; font-weight: 600; font-size: 12px; }
QLabel#headline { font-size: 27px; font-weight: 600; }
QLabel#brand { font-size: 25px; font-weight: 700; letter-spacing: 2px; }
QLabel#metric { font-size: 20px; font-weight: 600; }
QLabel#warning { color: #ffcf86; }
QPushButton { background: #273c47; border: 1px solid #41606d; border-radius: 8px;
              padding: 10px 16px; font-weight: 600; min-height: 20px; }
QPushButton:hover { background: #324f5c; border-color: #7ab8cf; }
QPushButton:focus { border-color: #c8fff0; }
QPushButton#primary { background: #35c987; color: #071c12; border-color: #35c987; }
QPushButton#primary:hover { background: #72e6b0; }
QPushButton:disabled, QPushButton#primary:disabled { color: #a5b5bd; background: #20303a; border-color: #30444e; }
QLineEdit, QComboBox, QSpinBox { background: #0c161d; border: 1px solid #4b6875;
                              border-radius: 7px; padding: 8px; min-height: 22px; }
QLineEdit:focus, QComboBox:focus, QSpinBox:focus { border-color: #70e6ae; }
QSpinBox::up-button, QSpinBox::down-button { background: #294451; width: 24px; border-left: 1px solid #4b6875; }
QSpinBox::up-button:hover, QSpinBox::down-button:hover { background: #426372; }
QSpinBox::up-arrow { image: url(SPIN_UP_IMAGE); width: 10px; height: 6px; }
QSpinBox::down-arrow { image: url(SPIN_DOWN_IMAGE); width: 10px; height: 6px; }
QComboBox QAbstractItemView { background: #182831; selection-background-color: #285742; }
QCheckBox { spacing: 10px; padding: 5px 0; background: transparent; }
QCheckBox:focus { background: #25453e; border-radius: 5px; }
QCheckBox::indicator { width: 20px; height: 20px; background: #0c161d;
                       border: 1px solid #6b8996; border-radius: 4px; }
QCheckBox::indicator:checked { image: url(CHECK_IMAGE); border-color: #70e6ae; }
QTabWidget::pane { border: none; }
QTabBar::tab { background: #182831; padding: 10px 17px; border-radius: 5px; margin-right: 5px; }
QTabBar::tab:selected { background: #2b5143; color: #baffdb; }
QPlainTextEdit { background: #080f14; color: #b3e8d4; border: 1px solid #304651;
                 border-radius: 8px; padding: 9px; selection-background-color: #375949; }
QProgressBar { border: none; background: #263c46; height: 5px; border-radius: 2px; }
QProgressBar::chunk { background: #35c987; }
QScrollArea { border: none; }
QScrollBar:vertical { background: #14232b; width: 12px; }
QScrollBar::handle:vertical { background: #4c6873; border-radius: 4px; min-height: 24px; }
'''


def label(text: str, style: str = '', wrap: bool = False) -> QLabel:
    widget = QLabel(text)
    widget.setTextFormat(Qt.TextFormat.PlainText)
    widget.setObjectName(style)
    widget.setWordWrap(wrap)
    return widget


class InformationPanel(QPlainTextEdit):
    """A stable text slot: long observations scroll instead of moving actions."""
    def __init__(self, text: str = '', lines: int = 3, name: str = 'Status information'):
        super().__init__()
        self.lines = lines
        self.setReadOnly(True)
        self.setAccessibleName(name)
        self.setFrameShape(QFrame.Shape.NoFrame)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setStyleSheet('QPlainTextEdit { background: transparent; color: #b3c4cd; '
                          'border: none; border-radius: 0; padding: 0; } '
                          'QPlainTextEdit#warning { color: #ffcf86; }')
        self.document().setDocumentMargin(0)
        self.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Fixed)
        self._fit_lines()
        self.setText(text)

    def setText(self, text: str):
        if text == self.toPlainText(): return
        self.setPlainText(text)
        self.verticalScrollBar().setValue(0)

    def text(self) -> str:
        return self.toPlainText()

    def _fit_lines(self):
        self.setFixedHeight(self.fontMetrics().lineSpacing() * self.lines + 8)

    def changeEvent(self, event):
        super().changeEvent(event)
        if event.type() == QEvent.Type.FontChange and hasattr(self, 'lines'):
            self._fit_lines()


def reserve_hidden_space(widget):
    policy = widget.sizePolicy()
    policy.setRetainSizeWhenHidden(True)
    widget.setSizePolicy(policy)


class WorkerSignals(QObject):
    output = Signal(str)
    finished = Signal(bool, str)

class EnrollmentSignals(QObject):
    comparison = Signal(object)


class ResultSignals(QObject):
    finished = Signal(object)


class ReadWorker(QRunnable):
    """One bounded background observation; its signal is applied on the UI thread."""
    def __init__(self, read):
        super().__init__()
        self.read = read
        self.signals = ResultSignals()

    def run(self):
        signals = self.signals  # Retain the emitter until run returns, even when the receiver releases the worker.
        try: result = self.read()
        except Exception: result = None  # Never expose private paths, input or tracebacks.
        signals.finished.emit(result)


def collect_status(root, config, secrets, reporter, tokens, asynchronous=True):
    processes = control.owned_hosts(root)
    health = read_status(root, {process.pid for process in processes})
    sample = None
    if tokens:
        if reporter is None:
            reader = control.host.TokenSampler if asynchronous else control.host.TokenReporter
            reporter = reader(providers=config['providers'], activity_dir=root/'tools/activity')
            reporter.poll_seconds = config['token_poll_s']
        sample = reporter.poll()
    working = bool(tokens and processes and reporter.last_use is not None and
                   time.monotonic() - reporter.last_use < 20)
    return {'running': bool(processes), 'summary': desktop.connection_summary(root, processes),
            'health': health, 'log': desktop.recent_log(root, secrets) if tokens else None,
            'sample': sample, 'reporter': reporter, 'working': working,
            'reader_state':reporter.read_state() if isinstance(reporter,control.host.TokenSampler) else None,
            'sessions': __import__('session_activity').summary(root/'tools/activity',config['providers']) if tokens else None}


class ActionWorker(QRunnable):
    def __init__(self, action, name: str):
        super().__init__()
        self.action, self.name = action, name
        self.signals = WorkerSignals()

    def run(self):
        signals = self.signals
        try:
            self.action(signals.output.emit)
            signals.finished.emit(True, self.name + ' complete.')
        except control.SetupError as error:
            signals.finished.emit(False, safe_text(str(error)))
        except Exception:
            # Exceptions from credentials, subprocesses or APIs may contain
            # private input. Never forward their raw text or traceback.
            signals.finished.emit(False, self.name + ' failed. Check settings and the action log.')


class FirmwareDialog(QDialog):
    def __init__(self, board_id: str, parent=None):
        super().__init__(parent)
        self.setWindowTitle('Prepare display firmware')
        self.setMinimumWidth(570)
        layout = QVBoxLayout(self)
        layout.addWidget(label(get_board(board_id).name, 'metric', True))
        self.kind = QComboBox()
        self.kind.addItem('First installation — resets display settings', 'install')
        self.kind.addItem('Update this project\'s existing installation', 'update')
        self.kind.setAccessibleName('Firmware operation')
        layout.addWidget(self.kind)
        layout.addWidget(label('For a factory demo or a different project, use First installation. '
                               'An update requires the existing AI Monitor partition layout.', 'muted', True))
        self.start_after = QCheckBox('Start the host after a successful firmware installation')
        self.start_after.setChecked(True)
        layout.addWidget(self.start_after)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)


class ConfirmFlashDialog(QDialog):
    def __init__(self, board_id: str, port: str, kind: str, parent=None):
        super().__init__(parent)
        self.setWindowTitle('Confirm verified firmware write')
        self.setMinimumWidth(580)
        layout = QVBoxLayout(self)
        board = get_board(board_id)
        layout.addWidget(label('Review before writing', 'headline'))
        layout.addWidget(label(f'Board: {board.name}\nChip: {board.chip}\nUSB port: {port}\n'
                               f'Operation: {"First installation" if kind == "install" else "Application update"}', wrap=True))
        if board.experimental:
            layout.addWidget(label('EXPERIMENTAL S3 — not verified on physical hardware. Use USB TO UART.', 'warning', True))
        layout.addWidget(label('Firmware hashes, chip headers and image layout passed verification. '
                               'First installation resets display settings. Keep power connected until completion.', 'muted', True))
        prompt = label('Type FLASH to enable the write button:')
        self.confirm = QLineEdit()
        self.confirm.setAccessibleName('Type FLASH to confirm')
        prompt.setBuddy(self.confirm)
        layout.addWidget(prompt)
        layout.addWidget(self.confirm)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Cancel)
        self.write = buttons.addButton('Write firmware', QDialogButtonBox.ButtonRole.AcceptRole)
        self.write.setEnabled(False)
        self.confirm.textChanged.connect(lambda text: self.write.setEnabled(text.strip() == 'FLASH'))
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)


class MonitorWindow(QMainWindow):
    def __init__(self, root: Path = control.ROOT, monitor: bool = True):
        super().__init__()
        self.root = root
        self.enrollment_signals = EnrollmentSignals(self)
        self.enrollment_signals.comparison.connect(self._compare_device_code, Qt.ConnectionType.QueuedConnection)
        self.busy = False
        self.unsaved = False
        self.worker = None
        self.secrets = []
        self.previous_log = None
        self.token_reporter = None
        self.close_after_stop = False
        self.close_stop_completed = False
        self.recover_after_action = False
        self.config_error = False
        self.monitor_enabled = monitor
        self.tray = None
        self.quit_requested = False
        self.hidden_to_tray = False
        self.visibility_generation = 0
        self.restoring_window = False
        self.restore_state = Qt.WindowState.WindowNoState
        self.restore_geometry = None
        self.restore_size = None
        self.usb_ports = []
        self.connection_checked = False
        self.connection_failed = False
        self.current_action = None
        self.pending_setup_report = None
        self.live_sampler = None
        self.cached_health = None
        self.live_connected = False
        self.host_running = False
        self.status_worker = None
        self.scan_worker = None
        self.status_epoch = 0
        self.closed = False
        self.cached_summary = 'CHECKING HOST STATUS'
        self.status_known = False
        self.auto_start_pending = False
        self.pending_flash = None
        self.deferred_observations = {}
        try:
            self.config = desktop.load_settings(root)
        except (ValueError, OSError):
            self.config_error = True
            self.config = dict(control.host.DEFAULT_CONFIG)
        self._remember_secrets()
        self.pool = QThreadPool(self)
        self.pool.setMaxThreadCount(1)
        self.status_pool = QThreadPool(self)
        self.status_pool.setMaxThreadCount(1)
        self.scan_pool = QThreadPool(self)
        self.scan_pool.setMaxThreadCount(1)
        self.setWindowTitle('AI Monitor — NOVA desktop companion')
        self.setWindowIcon(QIcon(str(ASSETS / 'nova-icon.png')))
        self.resize(1200, 900)
        self.setMinimumSize(1040, 760)
        self.setStyleSheet(STYLE.replace('CHECK_IMAGE', (ASSETS/'checked.png').as_posix())
                          .replace('SPIN_UP_IMAGE', (ASSETS/'spin-up.png').as_posix())
                          .replace('SPIN_DOWN_IMAGE', (ASSETS/'spin-down.png').as_posix()))
        self.ready_image = QPixmap(str(ASSETS / 'nova-done.png'))
        self.work_image = QPixmap(str(ASSETS / 'nova-work.png'))
        self.robot_pixmaps = tuple(image.scaled(230, 174, Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation) for image in (self.ready_image, self.work_image))
        self.robot_working = None
        self.robot_pose = None
        self.session_pixmaps={pose:QPixmap(str(ASSETS/('nova-'+pose+'.png'))).scaled(230,174,
            Qt.AspectRatioMode.KeepAspectRatio,Qt.TransformationMode.SmoothTransformation) for pose in ('attention','error')}
        self._build()
        self._load_fields()
        if self.config_error:
            self.notice.setText('Local settings could not be loaded. Your file was preserved. Use Recover invalid settings in Host settings.')
        self.append_output('Welcome. Choose your board and AI providers, then save settings.')
        self.append_output('The monitor reads usage records and quota status. It does not generate AI requests.')
        self.save_shortcut = QShortcut(QKeySequence.StandardKey.Save, self)
        self.save_shortcut.activated.connect(self.save)
        self.quit_shortcut = QShortcut(QKeySequence('Ctrl+Q'), self)
        self.quit_shortcut.activated.connect(self.request_quit)
        self.timer = QTimer(self)
        self.timer.setInterval(2500)
        self.timer.timeout.connect(self.refresh_status)
        self.tray_timer = QTimer(self)
        self.tray_timer.setInterval(10000)
        self.tray_timer.timeout.connect(self.refresh_tray)
        if monitor:
            self.auto_start_pending = bool(self.config['start_host_on_open'] and self.config.get('board') and self.config['providers'])
            self._create_tray()
            self.refresh_status()
            self.timer.start()

    def _auto_start_if_needed(self):
        if self.unsaved or self.config_error or self.closed: return
        if self.host_running:
            self.append_output('Existing host reused. No restart or extra quota request was needed.')
            self.refresh_status()
        else:
            self.start()

    def _create_tray(self):
        if self.closed or self.windowIcon().isNull(): return
        if self.tray is not None:
            self.tray.show()
            self.refresh_tray(poll=False)
            return
        self.tray = QSystemTrayIcon(self.windowIcon(), self)
        menu = self.tray_menu = QMenu(self)
        menu.addAction('Open AI Monitor', self.restore_from_tray)
        menu.addSeparator()
        self.tray_start = menu.addAction('Start host', self.start)
        self.tray_stop = menu.addAction('Stop host', self.stop)
        menu.addSeparator()
        self.tray_quit = menu.addAction('Quit AI Monitor', self.request_quit)
        self.tray.setContextMenu(menu)
        self.tray.activated.connect(self._tray_activated)
        self.tray.show()
        self._apply_preferences()
        self.refresh_tray()
        self.tray_timer.start()

    def _tray_available(self):
        return self.tray is not None and self.tray.isVisible() and QSystemTrayIcon.isSystemTrayAvailable()

    def refresh_tray(self, poll=True):
        if self.tray is None or self.closed: return
        if self.hidden_to_tray and not self._tray_available():
            self.restore_from_tray()
            self.notice.setText('The NOVA tray icon is unavailable. AI Monitor has reopened; use the taskbar or desktop shortcut.')
        if not self.tray.isVisible(): self.tray.show()
        if poll and self.hidden_to_tray and self.monitor_enabled: self.refresh_status()
        self.tray.setToolTip('AI Monitor • ' + self.cached_summary)
        self.tray_start.setEnabled(self.status_known and not self.busy and not self.host_running and not self.unsaved and
                                   bool(self.config.get('board') and self.config['providers']) and not self.config_error)
        self.tray_stop.setEnabled(not self.busy and self.host_running)
        self.tray_quit.setEnabled(not self.busy)
        self.tray_quit.setText('Quit AI Monitor — ' + ('keep host running' if self.config['keep_host_on_close'] else 'stop host'))

    def hide_to_tray(self):
        if self.closed or self.restoring_window: return False
        if not self._tray_available(): return False
        if self.hidden_to_tray: return True  # Keep the original state and geometry on duplicate hide requests.
        self.visibility_generation += 1
        if not self.isMinimized(): self._remember_geometry()
        self.restore_state = self.windowState() & ~Qt.WindowState.WindowMinimized
        self.hidden_to_tray = True
        self.status_epoch += 1
        self.hide()
        self.timer.stop()  # The independent host keeps monitoring; avoid duplicate UI database polling.
        self.refresh_tray()
        return True

    def restore_from_tray(self):
        if self.closed or self.restoring_window: return
        self.visibility_generation += 1  # Invalidate every deferred hide from an older minimize gesture.
        was_hidden = self.hidden_to_tray or self.isMinimized() or not self.isVisible()
        state = self.restore_state if self.hidden_to_tray else self.windowState()
        normal_size = self.restore_size
        self.restoring_window = True
        try:
            if self.hidden_to_tray and self.restore_geometry is not None:
                self.restoreGeometry(self.restore_geometry)
            # restoreGeometry can restore a minimized flag on Windows. Explicit
            # normal/maximized display commands always remove that flag.
            if state & Qt.WindowState.WindowFullScreen: self.showFullScreen()
            elif state & Qt.WindowState.WindowMaximized: self.showMaximized()
            else:
                self.showNormal()
                if was_hidden and normal_size is not None: self.resize(normal_size)
            self.hidden_to_tray = False
            self.raise_(); self.activateWindow()
        finally:
            self.restoring_window = False
        self._remember_geometry()
        if self.monitor_enabled:
            if was_hidden:
                self.status_epoch += 1
                self._reset_tokens()  # Resume with a baseline without replacing a blocked worker.
                self.refresh_status()
            self.timer.start()

    def activate_requested(self, page='show'):
        """Desktop shortcut/single-instance handoff uses the same visible restore path."""
        if page == 'firmware': self.tabs.setCurrentIndex(3)
        self.restore_from_tray()

    def _tray_activated(self, reason):
        if reason in (QSystemTrayIcon.ActivationReason.Trigger, QSystemTrayIcon.ActivationReason.DoubleClick):
            self.restore_from_tray()

    def request_quit(self):
        if self.busy:
            self.restore_from_tray()
            self.notice.setText('Wait for the current action to finish before quitting.')
            return
        self.quit_requested = True
        if self.unsaved: self.restore_from_tray()
        self.close()

    def changeEvent(self, event):
        super().changeEvent(event)
        if (event.type() == QEvent.Type.WindowStateChange and self.isMinimized() and
                hasattr(self, 'config') and not self.restoring_window and not self.closed and
                not self.hidden_to_tray and self.config.get('minimize_to_tray') and self._tray_available()):
            self.visibility_generation += 1
            generation = self.visibility_generation
            QTimer.singleShot(0, lambda: self._hide_minimized(generation))

    def _hide_minimized(self, generation=None):
        if generation is not None and generation != self.visibility_generation: return
        if self.isMinimized() and not self.closed and not self.restoring_window and not self.hidden_to_tray:
            self.hide_to_tray()

    def _remember_geometry(self):
        if self.isVisible() and not self.isMinimized() and not self.hidden_to_tray and not self.restoring_window:
            self.restore_geometry = self.saveGeometry()
            self.restore_size = self.normalGeometry().size() if self.isMaximized() or self.isFullScreen() else self.size()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if hasattr(self, 'hidden_to_tray'): self._remember_geometry()

    def moveEvent(self, event):
        super().moveEvent(event)
        if hasattr(self, 'hidden_to_tray'): self._remember_geometry()

    def _remember_secrets(self):
        for value in (self.config.get('zai_key', ''), os.environ.get('ZAI_API_KEY', '')):
            if value and value not in self.secrets:
                self.secrets.append(value)
        self.secrets = self.secrets[-8:]

    def _build(self):
        central = QWidget()
        self.setCentralWidget(central)
        layout = QHBoxLayout(central)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        sidebar = QFrame()
        sidebar.setObjectName('sidebar')
        sidebar.setFixedWidth(280)
        left = QVBoxLayout(sidebar)
        left.setContentsMargins(24, 28, 24, 28)
        left.setSpacing(16)
        left.addWidget(label('AI MONITOR', 'brand'))
        left.addWidget(label('YOUR AI, AT A GLANCE', 'eyebrow'))
        left.addStretch(1)
        self.nova = QLabel()
        self.nova.setAccessibleName('NOVA robot companion')
        self.nova.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.nova.setFixedHeight(174)
        left.addWidget(self.nova)
        left.addWidget(label('NOVA', 'headline'))
        left.addWidget(label('A little companion for the work\nhappening on your PC.', 'muted', True))
        self.host_state = InformationPanel('HOST STOPPED', 2, 'Host connection status')
        left.addWidget(self.host_state)
        self.token_state = InformationPanel('Waiting for selected token sources.', 3, 'Local token activity status')
        left.addWidget(self.token_state)
        self.live_state=InformationPanel('Agent USB: waiting for confirmation',2,'Agent event USB delivery status')
        left.addWidget(self.live_state)
        left.addStretch(2)
        self.close_hint = InformationPanel('', 4, 'Close and tray behavior')
        left.addWidget(self.close_hint)
        left.addWidget(label(APP_VERSION, 'eyebrow'))
        layout.addWidget(sidebar)

        right = QVBoxLayout()
        right.setContentsMargins(28, 26, 28, 24)
        right.setSpacing(15)
        layout.addLayout(right, 1)
        heading = QHBoxLayout()
        titles = QVBoxLayout()
        titles.addWidget(label('Your desk companion', 'headline'))
        titles.addWidget(label('Set up your display. Start the host. Let NOVA follow your work.', 'muted', True))
        heading.addLayout(titles, 1)
        heading.addWidget(label('USB COMPANION', 'eyebrow'))
        right.addLayout(heading)
        actions = QHBoxLayout()
        self.save_button = self._button('&Save settings', self.save, primary=True)
        self.start_button = self._button('&Start host', self.start, primary=True)
        self.stop_button = self._button('S&top host', self.stop)
        self.integration_button = self._button('Provider set&up', self.integrations)
        actions.addWidget(self.save_button, 1)
        actions.addWidget(self.start_button, 1)
        actions.addWidget(self.stop_button, 1)
        actions.addWidget(self.integration_button, 1)
        right.addLayout(actions)
        self.progress = QProgressBar()
        self.progress.setRange(0, 0)
        self.progress.setFixedHeight(5)
        reserve_hidden_space(self.progress)
        self.progress.hide()
        right.addWidget(self.progress)
        self.tabs = QTabWidget()
        self.tabs.addTab(self._setup_tab(), 'Setup')
        self.tabs.addTab(self._ai_tab(), 'AI setup')
        self.tabs.addTab(self._preferences_tab(), 'Host settings')
        self.tabs.addTab(self._firmware_tab(), 'Firmware')
        self.tabs.addTab(self._help_tab(), 'Help')
        from insights_ui import HistoryView
        self.history_view=HistoryView(self)
        history_scroll=QScrollArea(); history_scroll.setWidgetResizable(True); history_scroll.setWidget(self.history_view)
        self.tabs.addTab(history_scroll, 'History')
        from companion_ui import CompanionView
        self.companion_view=CompanionView(self)
        companion_scroll=QScrollArea();companion_scroll.setWidgetResizable(True);companion_scroll.setWidget(self.companion_view)
        self.tabs.addTab(companion_scroll,'Companions')
        right.addWidget(self.tabs, 1)
        console_heading = QHBoxLayout()
        console_heading.addWidget(label('COMPANION TERMINAL', 'eyebrow'))
        console_heading.addStretch()
        console_heading.addWidget(label('Read-only activity and connection messages', 'muted'))
        right.addLayout(console_heading)
        self.console_tabs = QTabWidget()
        self.activity = self._console('Application activity')
        self.host_log = self._console('Host connection log')
        self.console_tabs.addTab(self.activity, 'Activity')
        self.console_tabs.addTab(self.host_log, 'Host log')
        self.console_tabs.setMinimumHeight(145)
        self.console_tabs.setMaximumHeight(180)
        right.addWidget(self.console_tabs)
        self.notice = InformationPanel('Ready to configure. Nothing starts automatically.', 2, 'Action result and next step')
        right.addWidget(self.notice)
        self._show_robot(False)

    def _button(self, text, callback, primary=False):
        button = QPushButton(text)
        button.setFixedHeight(44)
        button.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Fixed)
        button.setAutoDefault(False)
        if primary:
            button.setObjectName('primary')
        button.clicked.connect(callback)
        button.released.connect(lambda: QTimer.singleShot(0, self._flush_observations))
        return button

    def _button_pressed(self):
        return any(button.isDown() for button in self.findChildren(QPushButton))

    def _flush_observations(self):
        # clicked runs before this queued flush. Finish the action the user saw
        # before applying observations that could change its route or caption.
        if self.closed or self._button_pressed(): return
        pending, self.deferred_observations = self.deferred_observations, {}
        if 'ports' in pending: self._scanned(pending['ports'])
        if 'status' in pending: self._status_finished(pending['status'])

    def _console(self, name: str):
        box = QPlainTextEdit()
        box.setReadOnly(True)
        box.setAccessibleName(name)
        box.setMaximumBlockCount(400)
        font = QFont('Consolas', 10)
        font.setStyleHint(QFont.StyleHint.Monospace)
        box.setFont(font)
        return box

    def _setup_tab(self):
        content = QWidget()
        form = QVBoxLayout(content)
        form.setContentsMargins(0, 15, 0, 0)
        form.setSpacing(10)
        form.addWidget(label('Choose your display and USB connection here. Choose your AIs in AI setup, '
                             'save settings, then install display firmware if needed and start the host.', 'muted', True))
        form.addWidget(label('SETUP PROGRESS', 'eyebrow'))
        self.setup_progress = InformationPanel('', 2, 'Setup progress')
        form.addWidget(self.setup_progress)
        self.setup_next = self._button('Continue setup', self.continue_setup, primary=True)
        form.addWidget(self.setup_next)
        form.addWidget(label('DISPLAY AND CONNECTION', 'eyebrow'))
        fields = QGridLayout()
        self.board = QComboBox()
        self.board.setAccessibleName('Display board')
        self.board.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon)
        self.board.setMinimumContentsLength(20)
        self.board.addItem('Choose your display board…', '')
        for item in BOARDS.values():
            name = 'Waveshare ESP32-S3 4.3" (experimental)' if item.experimental else 'GUITION ESP32-P4 (JC4880P433)'
            self.board.addItem(name, item.id)
            self.board.setItemData(self.board.count() - 1, item.name, Qt.ItemDataRole.ToolTipRole)
        self.port = QComboBox()
        self.port.setEditable(True)
        self.port.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon)
        self.port.setMinimumContentsLength(7)
        self.port.setAccessibleName('USB serial port')
        self.rescan_button = self._button('Rescan USB', self.rescan)
        self.rescan_button.setFixedWidth(126)
        self.check_usb_button = self._button('Check connection', self.check_connection)
        fields.addWidget(label('Display board'), 0, 0)
        fields.addWidget(label('USB port'), 0, 1)
        fields.addWidget(self.board, 1, 0)
        port_row = QHBoxLayout()
        port_row.addWidget(self.port, 1)
        port_row.addWidget(self.rescan_button)
        fields.addLayout(port_row, 1, 1)
        fields.setColumnStretch(0, 3)
        fields.setColumnStretch(1, 2)
        form.addLayout(fields)
        self.usb_help = InformationPanel('', 4, 'Available USB ports and connection help')
        form.addWidget(self.usb_help)
        form.addWidget(self.check_usb_button)
        self.connect_pc_button = self._button('Connect this PC to the display', self.connect_display_pc)
        form.addWidget(self.connect_pc_button)
        form.addWidget(label('Optional secure connection for future physical permissions. '
                             'Open MENU > SETTINGS > CONNECT PC, then tap CONNECT PC on that page. '
                             'Connecting does not enable AI approvals.', 'muted', True))
        self.board_help = InformationPanel('', 2, 'Selected display guidance')
        form.addWidget(self.board_help)
        form.addWidget(self._button('Choose and set up my AIs', lambda: self.tabs.setCurrentIndex(1), primary=True))
        form.addStretch()
        self.board.currentIndexChanged.connect(self._changed)
        self.port.currentTextChanged.connect(self._changed)
        scroll = QScrollArea(); scroll.setWidgetResizable(True); scroll.setWidget(content)
        return scroll

    def _ai_tab(self):
        content = QWidget(); form = QVBoxLayout(content)
        form.setContentsMargins(8, 15, 8, 15); form.setSpacing(10)
        form.addWidget(label('Choose the AIs you use, then save settings. Select an AI below to see its setup instructions.', 'muted', True))
        form.addWidget(label('CHOOSE YOUR AI PROVIDERS', 'eyebrow'))
        grid = QGridLayout()
        self.providers = {}
        for index, (key, (name, _, support)) in enumerate(PROVIDERS.items()):
            checkbox = QCheckBox(name)
            checkbox.setToolTip(support)
            checkbox.setAccessibleDescription(support)
            checkbox.toggled.connect(lambda checked, provider=key: self._provider_changed(provider, checked))
            grid.addWidget(checkbox, index // 2, index % 2)
            self.providers[key] = checkbox
        form.addLayout(grid)
        form.addWidget(label('Codex, ZCode, Claude Code, Gemini CLI and OpenCode have built-in local readers. '
                             'Copilot, Cursor and Antigravity require an advanced numeric bridge; selecting them alone cannot import editor usage.', 'warning', True))
        self.check_ai_button = self._button('Check AI setup', self.check_ai_setup)
        self.read_ai_button = self._button('Read AI instructions', self.read_ai_instructions)
        self.enter_key_button = self._button('Enter Z.AI key', self.enter_zai_key)
        self.enter_key_button.setToolTip('Select ZCode to enter or change its optional quota API key')
        setup_actions = QHBoxLayout()
        setup_actions.addWidget(self.check_ai_button, 1)
        setup_actions.addWidget(self.read_ai_button, 1)
        setup_actions.addWidget(self.enter_key_button, 1)
        form.addLayout(setup_actions)
        form.addWidget(label('SETUP INSTRUCTIONS FOR EACH AI', 'eyebrow'))
        self.provider_guide = QComboBox()
        self.provider_guide.setAccessibleName('AI provider setup instructions')
        for key, (name, _, _) in PROVIDERS.items():
            self.provider_guide.addItem(name, key)
        self.provider_guide.setCurrentIndex(-1)
        self.provider_guide.setPlaceholderText('Choose an AI to read its setup instructions')
        self.provider_instructions = InformationPanel(
            'Choose an AI above to see what it needs. No AI is preselected.', 6, 'Selected AI setup instructions')
        self.provider_link = self._button('Open official setup guide', self._open_provider_guide)
        self.provider_link.setEnabled(False)
        self.provider_guide.currentIndexChanged.connect(self._show_provider_guide)
        form.addWidget(self.provider_guide)
        form.addWidget(self.provider_instructions)
        form.addWidget(self.provider_link)
        self.codex_setup_button = self._button('Install / sign in Codex…', self._codex_setup)
        self.claude_link_button = self._button('Link Claude quota…', lambda: self.claude_quota(False))
        self.claude_unlink_button = self._button('Remove quota link…', lambda: self.claude_quota(True))
        self.claude_unlink_button.setToolTip('Remove only this installation\'s Claude quota link')
        # Two permanent action slots keep the guide, key and refresh controls
        # in the same place for every provider. Inactive actions remain hidden.
        self.provider_action_slot = QStackedWidget()
        self.provider_action_slot.addWidget(QWidget())
        self.provider_action_slot.addWidget(self.codex_setup_button)
        self.provider_action_slot.addWidget(self.claude_link_button)
        self.provider_remove_slot = QStackedWidget()
        self.provider_remove_slot.addWidget(QWidget())
        self.provider_remove_slot.addWidget(self.claude_unlink_button)
        bridge_row = QHBoxLayout()
        bridge_row.addWidget(self.provider_action_slot, 1)
        bridge_row.addWidget(self.provider_remove_slot, 1)
        self.provider_action_slot.setFixedHeight(44)
        self.provider_remove_slot.setFixedHeight(44)
        form.addLayout(bridge_row)
        self.claude_session_button=self._button('Link Claude session events…',lambda:self.claude_sessions(False))
        self.claude_session_remove=self._button('Remove session events…',lambda:self.claude_sessions(True))
        self.codex_session_button=self._button('Link Codex session events…',lambda:self.codex_sessions(False))
        self.codex_session_remove=self._button('Remove session events…',lambda:self.codex_sessions(True))
        self.zcode_session_button=self._button('Link ZCode session events…',lambda:self.zcode_sessions(False))
        self.zcode_session_remove=self._button('Remove session events…',lambda:self.zcode_sessions(True))
        self.session_action_slot=QStackedWidget()
        self.session_remove_slot=QStackedWidget()
        for slot,buttons in ((self.session_action_slot,(self.claude_session_button,self.codex_session_button,self.zcode_session_button)),
                             (self.session_remove_slot,(self.claude_session_remove,self.codex_session_remove,self.zcode_session_remove))):
            slot.addWidget(QWidget())
            for button in buttons: slot.addWidget(button)
            slot.setFixedHeight(44)
        session_row=QHBoxLayout()
        session_row.addWidget(self.session_action_slot,1)
        session_row.addWidget(self.session_remove_slot,1)
        form.addLayout(session_row)
        self.key_row = QWidget()
        key_layout = QHBoxLayout(self.key_row)
        key_layout.setContentsMargins(0, 0, 0, 0)
        self.key = QLineEdit()
        self.key.setEchoMode(QLineEdit.EchoMode.Password)
        self.key.setAccessibleName('Optional Z.AI API key')
        self.key.setPlaceholderText('Optional Z.AI key — leave empty to keep your saved key')
        self.clear_key = QCheckBox('Clear saved key')
        key_layout.addWidget(self.key, 1)
        key_layout.addWidget(self.clear_key)
        form.addWidget(self.key_row)
        self.key_row.setFixedHeight(44)
        reserve_hidden_space(self.key_row)
        form.addWidget(label('By default you can close this app after starting the host; it keeps running invisibly. '
                             'Change this in Host settings, or use Stop host.', 'muted', True))
        bottom = QHBoxLayout()
        bottom.addWidget(label('Quota refresh'))
        self.interval = QSpinBox()
        self.interval.setRange(15, 240)
        self.interval.setFixedWidth(118)
        self.interval.setSuffix(' sec')
        self.interval.setAccessibleName('Quota refresh interval in seconds')
        bottom.addWidget(self.interval)
        bottom.addStretch()
        bottom.addWidget(label('Status reads only — no model requests', 'muted', True), 1)
        form.addLayout(bottom)
        form.addStretch()
        self.key.textChanged.connect(self._changed)
        self.clear_key.toggled.connect(self._changed)
        self.interval.valueChanged.connect(self._changed)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(content)
        return scroll

    def _preferences_tab(self):
        content = QWidget()
        layout = QVBoxLayout(content)
        layout.setContentsMargins(8, 20, 8, 15)
        layout.addWidget(label('Background host preferences', 'headline'))
        layout.addWidget(label('Save settings to apply changes. USB recovery and token reads run independently of quota refresh. '
                               'A connected display does not guarantee that an AI account can report quota.', 'muted', True))
        self.reconnect = QSpinBox(); self.reconnect.setRange(2, 60); self.reconnect.setSuffix(' sec')
        self.reconnect.setAccessibleName('USB reconnect interval in seconds')
        self.token_poll = QSpinBox(); self.token_poll.setRange(2, 15); self.token_poll.setSuffix(' sec')
        self.token_poll.setAccessibleName('Local token read interval in seconds')
        self.log_size = QSpinBox(); self.log_size.setRange(10, 18); self.log_size.setSuffix(' pt')
        self.log_size.setAccessibleName('Terminal font size')
        grid = QGridLayout()
        grid.setVerticalSpacing(8)
        for row, (caption, field) in enumerate((('Retry USB connection', self.reconnect),
                ('Read local token activity', self.token_poll), ('Terminal text size', self.log_size))):
            field.setMinimumHeight(44)
            grid.setRowMinimumHeight(row, 44)
            text = label(caption); text.setBuddy(field)
            grid.addWidget(text, row, 0); grid.addWidget(field, row, 1)
            field.valueChanged.connect(self._changed)
        layout.addLayout(grid)
        self.auto_start = QCheckBox('Start the host when this app opens')
        self.keep_host = QCheckBox('Keep the host running when I quit AI Monitor')
        self.minimize_tray = QCheckBox('Minimize to the NOVA system tray icon')
        self.close_tray = QCheckBox('Close button hides the app in the system tray')
        self.history_enabled=QCheckBox('Keep local usage and session history (up to 30 days)')
        self.history_enabled.setToolTip('Opt-in: token increases, quota and fixed lifecycle events. Observed active time excludes waiting and long gaps. No prompts, tool arguments or keys.')
        self.usb_permissions=QCheckBox('Use physical Claude Code permissions over USB (preview)')
        self.usb_permissions.setToolTip('Requires Claude Code, P4, PC enrollment and separate display opt-in. Never enables automatic approvals.')
        for field in (self.auto_start, self.keep_host, self.minimize_tray, self.close_tray, self.history_enabled, self.usb_permissions):
            field.toggled.connect(self._changed); layout.addWidget(field)
        layout.addWidget(label('Physical permissions: connect this PC to the display, enable permissions on the display, '
            'select Claude, save this opt-in and link the permission helper below. '
            'Production approval remains disabled until the physical validation gates pass.', 'muted', True))
        self.permission_link=self._button('Link Claude permission helper…',lambda:self.claude_permissions(False))
        self.permission_unlink=self._button('Remove permission helper…',lambda:self.claude_permissions(True))
        permission_row=QHBoxLayout();permission_row.addWidget(self.permission_link);permission_row.addWidget(self.permission_unlink)
        layout.addLayout(permission_row)
        layout.addWidget(label('Click the NOVA icon near the clock to reopen. Right-click it for host controls and Quit. '
                               'Hiding or minimizing never stops the host or discards unsaved settings. '
                               'If a system tray is unavailable, the window uses normal minimize/close behavior.', 'muted', True))
        layout.addWidget(label('Automatic start is opt-in and applies when you open AI Monitor. It does not install a Windows service '
                               'or add a sign-in task. USB choices are still validated before starting.', 'muted', True))
        self.provider_health = InformationPanel(
            'Start the host to see provider health. Token activity and account quota are separate.', 8, 'Live provider health')
        layout.addWidget(label('LIVE PROVIDER HEALTH', 'eyebrow'))
        layout.addWidget(self.provider_health)
        self.hardware_diagnostics = InformationPanel(
            'Connect the host to read device memory. No estimated hardware values are shown.', 12, 'Device diagnostics')
        layout.addWidget(label('DEVICE DIAGNOSTICS', 'eyebrow'))
        layout.addWidget(self.hardware_diagnostics)
        self.device_screen_button = self._button("Device screen…", self.device_screen)
        layout.addWidget(self.device_screen_button)
        self.recover_button = self._button('Recover invalid settings…', self.recover_settings)
        reserve_hidden_space(self.recover_button)
        self.recover_button.setVisible(self.config_error)
        layout.addWidget(self.recover_button)
        layout.addWidget(label('Private settings stay in this installation folder. Updating this installer preserves them; '
                               'a portable copy in another folder uses its own settings. No keys are exported to GitHub.', 'muted', True))
        layout.addStretch()
        scroll = QScrollArea(); scroll.setWidgetResizable(True); scroll.setWidget(content)
        return scroll

    def device_screen(self):
        from desktop_mirror import MirrorDialog
        current = getattr(self, "mirror_dialog", None)
        if current is not None and current.isVisible():
            current.raise_(); current.activateWindow(); return
        self.mirror_dialog = MirrorDialog(self.root, self)
        self.mirror_dialog.finished.connect(lambda _: setattr(self, "mirror_dialog", None))
        self.mirror_dialog.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
        self.mirror_dialog.show()

    def _firmware_tab(self):
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(8, 20, 8, 15)
        layout.addWidget(label('The right image for your board', 'headline'))
        layout.addWidget(label('Save your board and USB selection in Setup first. '
                               'The installer checks firmware size, SHA-256, chip headers and factory/application consistency.', 'muted', True))
        layout.addWidget(label('Waveshare S3 is experimental and targets the original CH422G model only. '
                               'B/C variants are unsupported. Use USB TO UART. Intermediate dimming is visual.', 'warning', True))
        self.flash_button = self._button('Install / update &firmware…', self.flash, primary=True)
        layout.addWidget(self.flash_button)
        layout.addWidget(label('You will review the exact board, port and operation and type FLASH before writing. '
                               'The host is stopped only after confirmation. Choose automatic host start in the next dialog.', 'muted', True))
        layout.addWidget(label('Keep this window open while writing. Progress and errors stay in the Activity panel below. '
                               'firmware-flasher.exe is a command-line helper; use this button for normal installation.', 'muted', True))
        layout.addStretch()
        scroll = QScrollArea(); scroll.setWidgetResizable(True); scroll.setWidget(widget)
        return scroll

    def _help_tab(self):
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(8, 20, 8, 15)
        layout.addWidget(label('A few useful things to know', 'headline'))
        layout.addWidget(label('1. Choose the exact display board and at least one AI provider.\n'
                               '2. Save settings; finish provider setup when required.\n'
                               '3. Install firmware on a new display, then start the host.\n'
                               '4. Close this window; the host keeps running in the background.\n\n'
                               'Token activity starts with a baseline and can lag generation. '
                               'The monitor does not send prompts to AI models. '
                               'Your optional API key stays in local tools/aim_host.json; keep it private.', 'muted', True))
        layout.addWidget(self._button('Open setup guide', lambda: QDesktopServices.openUrl(QUrl('https://github.com/catorendal-a11y/ai-monitor-p4-s3/blob/main/docs/QUICK_START.md'))))
        layout.addWidget(self._button('Open provider guide', lambda: QDesktopServices.openUrl(QUrl('https://github.com/catorendal-a11y/ai-monitor-p4-s3/blob/main/docs/PROVIDERS.md'))))
        layout.addStretch()
        scroll = QScrollArea(); scroll.setWidgetResizable(True); scroll.setWidget(widget)
        return scroll

    def _load_fields(self):
        self.board.setCurrentIndex(max(0, self.board.findData(self.config.get('board', ''))))
        self.rescan()
        self.port.setCurrentText(self.config['port'])
        for key, checkbox in self.providers.items():
            checkbox.setChecked(key in self.config['providers'])
        self.interval.setValue(self.config['interval_s'])
        self.reconnect.setValue(self.config['reconnect_s'])
        self.token_poll.setValue(self.config['token_poll_s'])
        self.log_size.setValue(self.config['log_font_size'])
        self.auto_start.setChecked(self.config['start_host_on_open'])
        self.keep_host.setChecked(self.config['keep_host_on_close'])
        self.minimize_tray.setChecked(self.config['minimize_to_tray'])
        self.close_tray.setChecked(self.config['close_to_tray'])
        self.history_enabled.setChecked(self.config['usage_history'])
        self.usb_permissions.setChecked(self.config['usb_permissions'])
        self._apply_preferences()
        self.unsaved = False
        self._changed(mark=False)
        self.notice.setText('Saved setup loaded. Start the host when your display is connected.'
                            if self.config.get('board') and self.config['providers'] else
                            'Choose your board and AI providers. Save settings before starting.')

    def _changed(self, *_args, mark=True):
        if hasattr(self,'usb_permissions'):
            eligible=self.providers['claude'].isChecked() and self.board.currentData()=='guition-p4'
            self.usb_permissions.setEnabled(not self.busy and eligible)
            if not eligible and self.usb_permissions.isChecked():self.usb_permissions.setChecked(False)
        self.key_row.setVisible(self.providers['zcode'].isChecked())
        self.enter_key_button.setEnabled(not self.busy and self.providers['zcode'].isChecked())
        board_id = self.board.currentData()
        if board_id == 'waveshare-s3-43':
            self.board_help.setText('EXPERIMENTAL S3 • original CH422G model • use USB TO UART • visual dimming')
            self.board_help.setObjectName('warning')
        elif board_id == 'guition-p4':
            self.board_help.setText('GUITION JC4880P433 • USB data port • hardware PWM dimming')
            self.board_help.setObjectName('muted')
        else:
            self.board_help.setText('Choose your display. Use a USB data cable and an explicit port when several devices are connected.')
            self.board_help.setObjectName('muted')
        self.board_help.style().unpolish(self.board_help)
        self.board_help.style().polish(self.board_help)
        if mark:
            self.unsaved = True
            self.connection_checked = False
            self.connection_failed = False
            self.live_connected = False
            self.notice.setText('Unsaved changes — save before starting or preparing firmware.')
        self._update_setup_progress()

    def _usb_setup_issue(self):
        try: port = serial_port(self.port.currentText())
        except ValueError: return 'Enter a valid USB port, for example COM6.'
        board_id = self.board.currentData()
        if port == 'auto' and board_id in BOARDS:
            matches = sum(getattr(item, 'vid', None) in get_board(board_id).usb_vids for item in self.usb_ports)
            if matches > 1: return 'Several matching boards are connected. Select the display’s explicit COM port.'
        return ''

    def _update_setup_progress(self):
        if not hasattr(self, 'setup_next') or not hasattr(self, 'providers'): return
        chosen = [key for key, box in self.providers.items() if box.isChecked()]
        board_ready = self.board.currentData() in BOARDS
        issue = self._usb_setup_issue()
        self.setup_progress.setText('Display: ' + ('chosen' if board_ready else 'choose your board') +
            ' • USB: ' + ('choose board first' if not board_ready else 'needs selection' if issue else 'selected') +
            ' • AI providers: ' + str(len(chosen)) + ' selected • Settings: ' +
            ('not saved' if self.unsaved or not board_ready or not chosen else 'saved'))
        if self.config_error: caption = 'Recover settings in Host settings'
        elif not board_ready: caption = 'Next: choose your display board'
        elif issue: caption = 'Next: select the display USB port'
        elif not chosen: caption = 'Next: choose and set up my AIs'
        elif self.unsaved: caption = 'Next: save settings'
        elif self.live_connected: caption = 'Connected: view host and AI status'
        elif self.host_running: caption = 'Host running: view connection and AI status'
        elif self.connection_checked: caption = 'Next: start host'
        elif self.connection_failed: caption = 'Next: firmware and USB help'
        else: caption = 'Next: check the display connection'
        self.setup_next.setText(caption)
        self.start_button.setText('Restart host' if self.host_running else 'Start host')
        self.setup_next.setEnabled(not self.busy)
        self.start_button.setEnabled(not self.busy and not self.config_error and
            not self.unsaved and board_ready and bool(chosen) and not issue)
        ready = not self.busy and not self.config_error and not self.unsaved and board_ready and bool(chosen)
        for button in (self.check_usb_button, self.check_ai_button, self.flash_button):
            button.setEnabled(ready and (button is self.check_ai_button or not issue))
        self.codex_setup_button.setEnabled(ready and 'codex' in self.config['providers'])
        self.claude_link_button.setEnabled(ready and 'claude' in self.config['providers'])
        self.claude_unlink_button.setEnabled(ready and 'claude' in self.config['providers'])
        self.claude_session_button.setEnabled(ready and 'claude' in self.config['providers'])
        self.claude_session_remove.setEnabled(ready and 'claude' in self.config['providers'])
        self.codex_session_button.setEnabled(ready and 'codex' in self.config['providers'])
        self.codex_session_remove.setEnabled(ready and 'codex' in self.config['providers'])
        self.zcode_session_button.setEnabled(ready and 'zcode' in self.config['providers'])
        self.zcode_session_remove.setEnabled(ready and 'zcode' in self.config['providers'])
        self.permission_link.setEnabled(ready and 'claude' in self.config['providers'] and self.config.get('usb_permissions') is True)
        self.permission_unlink.setEnabled(ready and 'claude' in self.config['providers'])
        self.enter_key_button.setEnabled(not self.busy and self.providers['zcode'].isChecked())

    def continue_setup(self):
        if self.busy: return
        if self.config_error: self.tabs.setCurrentIndex(2); return
        if self.board.currentData() not in BOARDS:
            self.tabs.setCurrentIndex(0); self.board.setFocus(); self.board.showPopup(); return
        if self._usb_setup_issue():
            self.tabs.setCurrentIndex(0); self.port.setFocus()
            self.notice.setText(self._usb_setup_issue()); return
        if not any(box.isChecked() for box in self.providers.values()):
            self.tabs.setCurrentIndex(1); return
        if self.unsaved: self.save(); self._update_setup_progress(); return
        if self.live_connected or self.host_running: self.tabs.setCurrentIndex(2); return
        if self.connection_checked: self.start()
        elif self.connection_failed:
            self.tabs.setCurrentIndex(3)
            self.notice.setText('Check the saved USB port and cable. For a new/factory display, choose First installation here. '
                                'Firmware is written only after review and FLASH confirmation.')
        else: self.check_connection()

    def _provider_changed(self, provider, checked):
        if checked and hasattr(self, 'provider_guide'):
            self.provider_guide.setCurrentIndex(self.provider_guide.findData(provider))
        self._changed()

    def _show_provider_guide(self):
        key = self.provider_guide.currentData()
        self.provider_action_slot.setCurrentIndex(1 if key == 'codex' else 2 if key == 'claude' else 0)
        self.provider_remove_slot.setCurrentIndex(1 if key == 'claude' else 0)
        for slot in (self.session_action_slot,self.session_remove_slot):
            slot.setCurrentIndex(1 if key=='claude' else 2 if key=='codex' else 3 if key=='zcode' else 0)
        if key in PROVIDER_SETUP:
            self.provider_instructions.setText(PROVIDER_SETUP[key][0])
            self.provider_link.setEnabled(True)
        else:
            self.provider_instructions.setText('Choose an AI above to see what it needs. No AI is preselected.')
            self.provider_link.setEnabled(False)

    def _open_provider_guide(self):
        key = self.provider_guide.currentData()
        if key in PROVIDER_SETUP:
            QDesktopServices.openUrl(QUrl(PROVIDER_SETUP[key][1]))

    def read_ai_instructions(self):
        self.tabs.setCurrentIndex(1)
        scroll = self.tabs.widget(1)
        # Explicit navigation only: changing live status or provider choices
        # never scrolls the form or moves controls underneath the pointer.
        self.provider_guide.setFocus()
        scroll.verticalScrollBar().setValue(max(0, self.provider_guide.y() - 8))

    def enter_zai_key(self):
        if self.busy or not self.providers['zcode'].isChecked(): return
        self.tabs.setCurrentIndex(1)
        self.key.setFocus()
        self.tabs.widget(1).ensureWidgetVisible(self.key_row, 0, 0)

    def check_ai_setup(self):
        if self._ready():
            from provider_setup import setup_report
            def check(emit):
                self.pending_setup_report=setup_report(self.root)
                for item in self.pending_setup_report:
                    emit(PROVIDERS[item['provider']][0]+': activity '+item['activity']+'; quota '+item['quota']+
                         '; display '+item['display']+'; events '+item['events']+'; '+item['live_usb'])
            self._run('Checking AI setup',check)

    def claude_sessions(self,remove):
        if not self._ready() or 'claude' not in self.config['providers']: return
        question=('Remove only this installation\'s observational Claude session hooks? Other hooks are preserved.' if remove else
            'Link Claude session events? A private settings backup is kept and other hooks are preserved. '
            'This records a hashed session ID and state only. It never approves tools, reads transcripts or returns context to Claude. '
            'Restart Claude Code after linking.')
        answer=QMessageBox.question(self,'Claude session events',question,
            QMessageBox.StandardButton.Yes|QMessageBox.StandardButton.No,QMessageBox.StandardButton.No)
        if answer!=QMessageBox.StandardButton.Yes: return
        from provider_setup import claude_session_link
        def update(emit):
            try: emit(claude_session_link(self.root,remove=remove))
            except ValueError as error: raise control.SetupError(str(error)) from None
        self._run('Updating Claude session events',update)

    def claude_permissions(self,remove):
        if not self._ready() or 'claude' not in self.config['providers']:return
        if not remove and self.config.get('usb_permissions') is not True:return
        question=('Remove only this installation\'s interactive permission helper? Other hooks and rules are preserved.' if remove else
            'Install the separate Claude PermissionRequest helper? A private settings backup is kept. '
            'It requires an enrolled PC, display opt-in and a separate physical hold for each approval. '
            'Unavailable requests use Claude permission handling. It does not grant permanent permission rules. '
            'Production physical approval is still gated by validation. Restart Claude Code after setup.')
        answer=QMessageBox.question(self,'Claude physical permissions',question,
            QMessageBox.StandardButton.Yes|QMessageBox.StandardButton.No,QMessageBox.StandardButton.No)
        if answer!=QMessageBox.StandardButton.Yes:return
        from claude_permission_setup import update
        self._run('Updating Claude permission helper',lambda emit:emit(update(self.root,remove=remove,opted_in=self.config.get('usb_permissions') is True)))

    def codex_sessions(self,remove):
        if not self._ready() or 'codex' not in self.config['providers']: return
        question=('Remove only this installation\'s observational Codex hooks? Other hooks are preserved.' if remove else
            'Link Codex session events? A private hooks backup is kept. Only state and hashed IDs are recorded. '
            'No commands, transcripts, context or permission decisions are returned. '
            'After linking, review and trust the hooks using /hooks in Codex and restart the session. '
            'Existing custom hooks are preserved; your Codex version must support lifecycle hooks.')
        answer=QMessageBox.question(self,'Codex session events',question,
            QMessageBox.StandardButton.Yes|QMessageBox.StandardButton.No,QMessageBox.StandardButton.No)
        if answer!=QMessageBox.StandardButton.Yes: return
        from provider_setup import codex_session_link
        def update(emit):
            try: emit(codex_session_link(self.root,remove=remove))
            except ValueError as error: raise control.SetupError(str(error)) from None
        self._run('Updating Codex session events',update)

    def zcode_sessions(self,remove):
        if not self._ready() or 'zcode' not in self.config['providers']:return
        question=('Remove only this installation\'s ZCode observer hooks?' if remove else
            'Link ZCode session events? A private settings backup is kept and other hooks are preserved. '
            'Only state and hashed IDs are recorded; no context or permission decisions are returned. '
            'Existing global hook disablement is preserved. Start a new ZCode session after linking.')
        answer=QMessageBox.question(self,'ZCode session events',question,
            QMessageBox.StandardButton.Yes|QMessageBox.StandardButton.No,QMessageBox.StandardButton.No)
        if answer!=QMessageBox.StandardButton.Yes:return
        from provider_setup import zcode_session_link
        self._run('Updating ZCode session events',lambda emit:emit(zcode_session_link(self.root,remove=remove)))

    def claude_quota(self, remove):
        if not self._ready() or 'claude' not in self.config['providers']: return
        text = ('Remove only this installation\'s Claude statusline link? Other Claude settings and local token activity are preserved.' if remove else
                'Link Claude subscription quota using its official statusline? A private backup is kept. Existing custom statuslines are preserved. '
                'The link reads numeric quota fields; it does not make model requests.')
        answer = QMessageBox.question(self, 'Claude quota link', text,
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No, QMessageBox.StandardButton.No)
        if answer != QMessageBox.StandardButton.Yes: return
        from provider_setup import claude_bridge
        def action(emit):
            try: emit(claude_bridge(self.root, remove=remove))
            except ValueError as error: raise control.SetupError(str(error)) from None
        self._run('Updating Claude quota link', action)

    def rescan(self):
        if self.monitor_enabled:
            if self.scan_worker is not None or self.closed: return
            self.usb_help.setText('Scanning USB ports in the background. Your selected port is preserved.')
            self.rescan_button.setEnabled(False)
            self.scan_worker = ReadWorker(lambda: sorted(control.list_ports.comports(), key=lambda p: p.device))
            self.scan_worker.signals.finished.connect(self._scanned, Qt.ConnectionType.QueuedConnection)
            self.scan_pool.start(self.scan_worker)
        else:
            try: ports = sorted(control.list_ports.comports(), key=lambda p: p.device)
            except OSError: ports = None
            self._scanned(ports)

    @Slot(object)
    def _scanned(self, ports):
        self.scan_worker = None
        if self.closed: return
        if self._button_pressed():
            self.deferred_observations['ports'] = ports
            return
        self.deferred_observations.pop('ports', None)
        self.rescan_button.setEnabled(not self.busy)
        # Preserve the current edit, even when it changed during the scan.
        current = self.port.currentText() or self.config['port']
        with QSignalBlocker(self.port):
            self.port.clear()
            self.port.addItem('auto')
            if ports is None:
                self.usb_ports = []
                self.usb_help.setText('USB scan unavailable. Enter your explicit port and check the connection.')
                self.port.setCurrentText(current)
                self._update_setup_progress()
                return
            self.usb_ports = ports
            for item in ports:
                self.port.addItem(safe_text(item.device))
                self.port.setItemData(self.port.count()-1, safe_text(item.description), Qt.ItemDataRole.ToolTipRole)
            self.port.setCurrentText(current)
        descriptions = [safe_text(item.device + ': ' + item.description, 100) for item in ports]
        self.usb_help.setText(('Available: ' + ' | '.join(descriptions) + '\nAuto requires exactly one matching USB device. '
                              'With several devices, select the display port explicitly.') if ports else
                             'No USB ports found. Connect a USB data cable, then Rescan USB. Your saved port is preserved.')
        self._update_setup_progress()

    def _error(self, text: str):
        if self.hidden_to_tray: self.restore_from_tray()
        self.notice.setText(text)
        self.append_output(text)
        QMessageBox.warning(self, 'Check your settings', text)

    def save(self):
        if self.busy:
            return
        if self.config_error:
            self._error('Recover the invalid local configuration in Host settings before saving. The original file is preserved.')
            return
        previous_providers = self.config['providers']
        try:
            self.config = desktop.save_settings(self.root, self.board.currentData(),
                [key for key, checkbox in self.providers.items() if checkbox.isChecked()],
                self.port.currentText(), self.interval.value(), self.key.text(), self.clear_key.isChecked(),
                options={'reconnect_s': self.reconnect.value(), 'token_poll_s': self.token_poll.value(),
                         'log_font_size': self.log_size.value(), 'start_host_on_open': self.auto_start.isChecked(),
                         'keep_host_on_close': self.keep_host.isChecked(),
                         'minimize_to_tray': self.minimize_tray.isChecked(), 'close_to_tray': self.close_tray.isChecked(),
                         'usage_history':self.history_enabled.isChecked(), 'usb_permissions':self.usb_permissions.isChecked()})
        except (control.SetupError, ValueError, OSError):
            self._error('Choose a supported board, at least one provider and a valid USB port. '
                        'API keys must be a single printable token. Nothing was saved.')
            return
        self._remember_secrets()
        self.key.clear()
        self.clear_key.setChecked(False)
        self.unsaved = False
        self.live_connected = False
        self.status_epoch += 1
        self.cached_health = None
        self._reset_tokens()
        self._apply_preferences()
        self._update_setup_progress()
        self.notice.setText('Settings saved. Existing keys were preserved unless you explicitly changed or cleared them.')
        self.append_output('Settings saved. Board: ' + get_board(self.config['board']).name)
        if 'codex' in self.config['providers'] and 'codex' not in previous_providers:
            answer = QMessageBox.question(self, 'Finish Codex setup',
                'Codex is selected. Open the official CLI setup console now? '
                'Installation and sign-in are offered only when needed.',
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.Yes)
            if answer == QMessageBox.StandardButton.Yes:
                self._codex_setup()

    def _ready(self):
        if self.config_error or self.unsaved or not self.config.get('board') or not self.config['providers']:
            self._error('Choose your display board in Display setup and your providers in AI setup, then Save settings.')
            return False
        return not self.busy

    def _run(self, name, action):
        if self.busy:
            return
        self.busy = True
        self.current_action = name
        for button in (self.start_button, self.stop_button, self.save_button,
                       self.flash_button, self.integration_button, self.rescan_button, self.check_usb_button):
            button.setEnabled(False)
        self.tabs.setEnabled(False)
        self.setup_next.setEnabled(False)
        self.progress.show()
        self.console_tabs.setCurrentIndex(0)
        self.notice.setText(name + '…')
        self.refresh_tray()
        self.worker = ActionWorker(action, name)
        self.worker.signals.output.connect(self.append_output, Qt.ConnectionType.QueuedConnection)
        self.worker.signals.finished.connect(self._finished, Qt.ConnectionType.QueuedConnection)
        self.pool.start(self.worker)

    @Slot(bool, str)
    def _finished(self, success, message):
        action_name = self.current_action
        if self.current_action == 'Checking USB identity':
            self.connection_checked = success
            self.connection_failed = not success
        self.current_action = None
        self.busy = False
        self.progress.hide()
        self.tabs.setEnabled(True)
        for button in (self.start_button, self.stop_button, self.save_button,
                       self.flash_button, self.integration_button, self.rescan_button, self.check_usb_button):
            button.setEnabled(True)
        self.notice.setText(message)
        self.append_output(message)
        self.worker = None
        if not success:
            self.quit_requested = False
            if self.hidden_to_tray: self.restore_from_tray()
            QMessageBox.warning(self, 'Action could not finish', message)
        elif message == 'Checking USB identity complete.':
            self.notice.setText('Display verified. Start the host if it is stopped; otherwise check AI status in Host settings.')
        if self.recover_after_action:
            self.recover_after_action = False
            if success:
                self.config = desktop.load_settings(self.root)
                self.config_error = False
                self.recover_button.hide()
                self._load_fields()
                self.append_output('Settings reset. The original file was backed up locally; keep that backup private.')
        self.refresh_status()
        self.refresh_tray()
        self._update_setup_progress()
        if self.close_after_stop:
            self.close_after_stop = False
            if success:
                self.close_stop_completed = True
                self.close()
        if action_name == 'Verifying firmware':
            prepared = self.pending_flash
            self.pending_flash = None
            if success and prepared is not None: self._confirm_flash(*prepared)
        if action_name == 'Checking AI setup':
            prepared,self.pending_setup_report=self.pending_setup_report,None
            if success and prepared is not None:
                from insights_ui import SetupReportDialog
                if self.hidden_to_tray: self.restore_from_tray()
                dialog=SetupReportDialog(prepared,self)
                if dialog.exec()==QDialog.DialogCode.Accepted and dialog.provider():
                    self.provider_guide.setCurrentIndex(self.provider_guide.findData(dialog.provider()))
                    self.read_ai_instructions()

    def start(self):
        if self._usb_setup_issue():
            self.restore_from_tray()
            self.tabs.setCurrentIndex(0)
            self.port.setFocus()
            self.notice.setText(self._usb_setup_issue())
            return
        if self._ready():
            self._run('Starting host', lambda emit: control.start_host(self.root, emit=emit))

    def stop(self):
        self._run('Stopping host', lambda emit: control.stop_host(self.root, emit=emit))

    def check_connection(self):
        if self._ready():
            self._run('Checking USB identity', lambda emit: desktop.check_connection(self.root, emit))

    def recover_settings(self):
        if self.busy or not self.config_error: return
        answer = QMessageBox.question(self, 'Recover local settings',
            'Keep a private backup of the original file, stop this installation\'s host and reset setup? '
            'You will choose your board/providers and enter your API key again. The backup stays on this PC.',
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No, QMessageBox.StandardButton.No)
        if answer != QMessageBox.StandardButton.Yes: return
        self.recover_after_action = True
        self._run('Recovering local settings', lambda emit: desktop.reset_invalid_settings(self.root, emit=emit))

    def connect_display_pc(self):
        if not self._ready(): return
        from enrollment_setup import connect_device
        answer = QMessageBox.question(self, 'Connect this PC',
            'Start the host, open MENU > SETTINGS > CONNECT PC on the display, '
            'then tap CONNECT PC on that page to open code comparison. '
            'Keep the display awake. Click Yes when the comparison screen is open. '
            'The host will pause briefly and return after setup. AI approvals remain disabled.',
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No, QMessageBox.StandardButton.No)
        if answer == QMessageBox.StandardButton.Yes:
            self._run('Connecting PC to display', lambda emit: connect_device(self.root, self.enrollment_signals.comparison.emit, emit))

    @Slot(object)
    def _compare_device_code(self, prompt):
        dialog = QDialog(self); dialog.setWindowTitle('Compare PC and display codes'); dialog.setMinimumWidth(560)
        layout = QVBoxLayout(dialog)
        layout.addWidget(label('Only connect if every group matches', 'headline', True))
        code = label(prompt.code, 'metric', True); code.setAccessibleName('PC display connection comparison code')
        layout.addWidget(code)
        layout.addWidget(label('Compare with the physical display. Hold HOLD TO CONFIRM there for 1.8 seconds, '
                               'then choose Codes match here. Cancel if anything differs.', 'muted', True))
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Cancel)
        match = buttons.addButton('Codes match', QDialogButtonBox.ButtonRole.AcceptRole)
        match.setAutoDefault(False); match.setDefault(False)
        buttons.accepted.connect(dialog.accept); buttons.rejected.connect(dialog.reject); layout.addWidget(buttons)
        timer = QTimer(dialog); timer.setSingleShot(True); timer.timeout.connect(dialog.reject); timer.start(45000)
        cancelled = QTimer(dialog); cancelled.timeout.connect(lambda: dialog.reject() if prompt.cancelled else None); cancelled.start(100)
        prompt.decide(dialog.exec() == QDialog.DialogCode.Accepted)
        dialog.deleteLater()

    def _apply_preferences(self):
        if self.config['close_to_tray']:
            hint = 'Close hides the app in the NOVA tray.\nUse the tray menu to Quit.'
        else:
            hint = 'Quit keeps your host running.' if self.config['keep_host_on_close'] else 'Quit stops this installation\'s host.'
        self.close_hint.setText('LOCAL RECORDS + USB\n' + hint)
        for box in (self.activity, self.host_log):
            box.setStyleSheet('QPlainTextEdit { font-family: "Consolas"; font-size: ' +
                              str(self.config['log_font_size']) + 'pt; }')

    def integrations(self):
        self.tabs.setCurrentIndex(1)
        choices = [key for key, field in self.providers.items() if field.isChecked()]
        if choices: self.provider_guide.setCurrentIndex(self.provider_guide.findData(choices[0]))

    def _codex_setup(self):
        if not self._ready():
            return
        if 'codex' not in self.config['providers']:
            self._error('Select Codex and save settings first.'); return
        try:
            desktop.open_integrations(self.root, codex_only=True)
            self.append_output('Official Codex setup opened in its own console. Follow its installation/sign-in prompts there.')
        except (control.SetupError, OSError):
            self._error('Provider setup could not open. Check that the complete package is extracted.')

    def flash(self):
        if not self._ready():
            return
        board_id = self.config['board']
        operation = FirmwareDialog(board_id, self)
        if operation.exec() != QDialog.DialogCode.Accepted:
            return
        kind = operation.kind.currentData()
        start_after = operation.start_after.isChecked()
        def prepare(emit):
            port, _command = desktop.prepare_flash(self.root, board_id, kind)
            self.pending_flash = (board_id, port, kind, start_after)
            emit('Firmware files verified. Review the selected board and USB port before writing.')
        self._run('Verifying firmware', prepare)

    def _confirm_flash(self, board_id, port, kind, start_after):
        if self.hidden_to_tray: self.restore_from_tray()
        confirm = ConfirmFlashDialog(board_id, port, kind, self)
        if confirm.exec() != QDialog.DialogCode.Accepted or confirm.confirm.text().strip() != 'FLASH':
            self.append_output('Firmware cancelled. Host and display were not changed.')
            return
        def install(emit):
            desktop.write_firmware(self.root, board_id, kind, port, emit)
            if start_after:
                control.start_host(self.root, emit=emit)
                emit('Firmware written and host process started. Check USB and provider health in Host settings. ' +
                     ('You may close this window; the host stays running.' if self.config['keep_host_on_close'] else
                      'Your Host settings stop the host when this window closes.'))
        self._run('Writing firmware', install)

    @Slot(str)
    def append_output(self, text: str):
        for secret in self.secrets:
            text = text.replace(secret, '[REDACTED]')
        self.activity.appendPlainText(f'[{datetime.now():%H:%M:%S}] {safe_text(text)}')

    def _show_robot(self, working: bool):
        pose='work' if working else 'done'
        if self.robot_working == working and self.robot_pose==pose: return
        self.robot_working = working
        self.robot_pose=pose
        self.nova.setPixmap(self.robot_pixmaps[int(working)])

    def _show_session_robot(self,pose):
        if self.robot_pose==pose: return
        self.robot_pose=pose; self.robot_working=False
        self.nova.setPixmap(self.session_pixmaps[pose])

    def _reset_tokens(self):
        if isinstance(self.token_reporter,control.host.TokenSampler):
            self.token_reporter.configure(self.config['providers'])
            self.token_reporter.poll_seconds=self.config['token_poll_s']
        else: self.token_reporter=None

    def refresh_status(self):
        if self.closed or self.status_worker is not None: return
        if not self.hidden_to_tray and self.token_reporter is None:
            reader=control.host.TokenSampler if self.monitor_enabled else control.host.TokenReporter
            self.token_reporter=reader(providers=self.config['providers'],activity_dir=self.root/'tools/activity')
            self.token_reporter.poll_seconds=self.config['token_poll_s']
        epoch = self.status_epoch
        config = dict(self.config, providers=list(self.config['providers']))
        root, secrets, reporter = self.root, tuple(self.secrets), self.token_reporter
        tokens = not self.hidden_to_tray
        def read():
            try: data = collect_status(root, config, secrets, reporter, tokens, self.monitor_enabled)
            except Exception: data = None
            # Failed reads belong to the same generation as successful reads.
            # An old failure must not clear a new setup's verified connection.
            return epoch, data
        if not self.monitor_enabled:
            # Explicit synchronous mode for offscreen fixtures and benchmarks.
            try: result = read()
            except Exception: result = None
            self._status_finished(result)
            return
        self.status_worker = ReadWorker(read)
        self.status_worker.signals.finished.connect(self._status_finished, Qt.ConnectionType.QueuedConnection)
        self.status_pool.start(self.status_worker)

    @Slot(object)
    def _status_finished(self, result):
        self.status_worker = None
        if self.closed: return
        if self._button_pressed():
            self.deferred_observations['status'] = result
            return
        self.deferred_observations.pop('status', None)
        if result is None:
            data = None
        else:
            epoch, data = result
            if epoch != self.status_epoch: return
        if data is None:
            self.cached_health = None
            self.status_known = False
            self.live_connected = False
            self.cached_summary = 'STATUS UNAVAILABLE — OPEN AI MONITOR'
            self.host_state.setText(self.cached_summary)
            self.provider_health.setText('Provider status unconfirmed. Check the host log or retry the status read.')
            self.hardware_diagnostics.setText('Device telemetry unavailable. Reconnect the host to sample again.')
            self.token_state.setText('Local status unavailable; check the host log.')
            self.live_state.setText('Agent USB: status unavailable')
            self._show_robot(False)
            self._update_setup_progress()
            self.refresh_tray(poll=False)
            return
        running = data['running']
        self.status_known = True
        self.host_running = running
        self.cached_summary = data['summary']
        self.host_state.setText(data['summary'])
        health = data['health']
        self.cached_health=health
        from host_status import live_status_text
        self.live_state.setText(live_status_text(health))
        if not self.hidden_to_tray:
            from hardware_presentation import hardware_text
            self.hardware_diagnostics.setText(hardware_text(health))
        self.token_reporter = data['reporter']
        if not self.hidden_to_tray:
            states = health.get('providers', {}) if health else {}
            self.live_connected = bool(health and health['state'] == 'connected' and
                health.get('board') == self.config.get('board') and
                self.config['port'] in ('auto', health.get('port')))
            self._update_setup_progress()
            captions = {'ready': 'quota received', 'unavailable': 'quota unavailable — check Host log / Provider setup',
                        'activity_only': 'activity only; no account quota'}
            self.provider_health.setText('\n'.join(PROVIDERS[key][0] + ': ' + captions.get(states.get(key),
                'waiting for quota status' if running else 'host stopped') for key in self.config['providers']) or
                'Choose your AI providers in AI setup.')
            text = data['log']
            if text != self.previous_log:
                scrollbar = self.host_log.verticalScrollBar()
                follow = scrollbar.value() == scrollbar.maximum()
                position = scrollbar.value()
                self.host_log.setPlainText(text or 'No host messages yet. Start the host after saving settings.')
                scrollbar.setValue(scrollbar.maximum() if follow else position)
                self.previous_log = text
            sample = data['sample']
            if sample:
                if not sample['known']:
                    self.token_state.setText('Waiting for readable token sources.')
                elif sample['seen']:
                    self.token_state.setText(f'Last recorded increase: {sample["idleSeconds"]} sec ago')
                else:
                    self.token_state.setText('Token sources readable. Baseline established.')
            self._show_robot(data['working'])
            sessions=data.get('sessions')
            if sessions and sessions.get('providers'):
                from session_activity import aggregate
                counts=aggregate(sessions)
                if counts['waiting']:
                    self.token_state.setText(f'SESSION EVENTS: {counts["waiting"]} waiting for you')
                    self._show_session_robot('attention')
                elif counts['running']:
                    self.token_state.setText(f'SESSION EVENTS: {counts["running"]} running')
                    self._show_robot(True)
                elif counts['error']:
                    self.token_state.setText('SESSION EVENTS: a turn ended with an error')
                    self._show_session_robot('error')
                elif counts['completed']:
                    self.token_state.setText('SESSION EVENTS: turn complete')
                    self._show_robot(False)
            if data.get('reader_state')=='stalled':
                recovery='DESKTOP TOKEN READER STALLED / Quit and reopen AI Monitor.'
                if health and health.get('local_reader')=='stalled': recovery+=' Restart host too.'
                self.token_state.setText(recovery)
            elif health and health.get('local_reader')=='stalled':
                self.token_state.setText('TOKEN READER STALLED / Restart host to retry local activity.')
        self.refresh_tray(poll=False)
        if self.auto_start_pending:
            self.auto_start_pending = False
            self._auto_start_if_needed()

    def closeEvent(self, event):
        if not self.quit_requested and self.config.get('close_to_tray') and self.hide_to_tray():
            event.ignore(); return
        if self.busy:
            self.notice.setText('Wait for the current action to finish before closing this window.')
            event.ignore()
            return
        if self.unsaved:
            answer = QMessageBox.question(self, 'Unsaved settings', 'Close without saving your changes?',
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No, QMessageBox.StandardButton.No)
            if answer != QMessageBox.StandardButton.Yes:
                self.quit_requested = False
                event.ignore(); return
            self.unsaved = False
        if not self.config['keep_host_on_close'] and not self.close_stop_completed:
            self.close_after_stop = True
            event.ignore()
            self.stop()
            return
        self.timer.stop()
        self.tray_timer.stop()
        self.closed = True
        if isinstance(self.token_reporter,control.host.TokenSampler): self.token_reporter.close()
        if self.live_sampler is not None: self.live_sampler.close()
        if self.tray is not None: self.tray.hide()
        event.accept()  # The independent background host is deliberately left running.
        if self.monitor_enabled: QTimer.singleShot(0, QApplication.instance().quit)


def run_desktop(firmware: bool = False) -> int:
    application = QApplication.instance() or QApplication(sys.argv[:1])
    application.setQuitOnLastWindowClosed(False)  # Tray lifetime ends only through the explicit, validated Quit path.
    application.setApplicationName('AI Monitor')
    application.setOrganizationName('AI Monitor contributors')
    application.setStyle('Fusion')
    try:
        from desktop_instance import DesktopInstance
        instance = DesktopInstance(control.ROOT)
        if not instance.claim(firmware): return 0
        window = MonitorWindow()
    except (ValueError, OSError, RuntimeError):
        QMessageBox.critical(None, 'Configuration unavailable',
            'AI Monitor could not open. If it is already running, use the NOVA tray icon. '
            'Otherwise use a writable folder and check the local settings. Your file was not changed.')
        return 1
    instance.requested.connect(window.activate_requested)
    if firmware:
        window.tabs.setCurrentIndex(3)
    window.show()
    try: return application.exec()
    finally: instance.close()
