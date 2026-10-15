"""Explicit, read-only device captures; never virtual touch or simulated pixels."""
import sys
import time
from datetime import datetime
from PySide6.QtCore import QTimer, Qt
from PySide6.QtGui import QImage, QPixmap
from PySide6.QtWidgets import QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton
import mirror_service


class MirrorDialog(QDialog):
    def __init__(self, root, parent=None):
        super().__init__(parent)
        self.root, self.nonce, self.started, self.stamp = root, None, 0, None
        self.capture_failed = False
        self.setWindowTitle('Device screen — real USB capture')
        self.setMinimumSize(850, 600)
        layout = QVBoxLayout(self)
        self.status = QLabel('Capture the connected device screen. No virtual touch or approval controls.')
        self.status.setWordWrap(True); layout.addWidget(self.status)
        self.image = QLabel('No device image captured')
        self.image.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.image.setMinimumSize(800, 480); layout.addWidget(self.image)
        row = QHBoxLayout()
        self.capture_button = QPushButton('Capture / Refresh')
        self.capture_button.setMinimumHeight(44)
        self.capture_button.clicked.connect(self.capture)
        row.addWidget(self.capture_button)
        close = QPushButton('Close'); close.setMinimumHeight(44); close.clicked.connect(self.reject)
        row.addWidget(close); layout.addLayout(row)
        self.timer = QTimer(self); self.timer.timeout.connect(self.poll); self.timer.start(250)

    def capture(self):
        if self.nonce: return
        try:
            self.nonce = mirror_service.request(self.root)
            self.started = time.monotonic()
            self.capture_failed = False
            self.capture_button.setEnabled(False)
            self.status.setText('Capturing through the running host. Existing image is STALE. Permission and connection-code screens are hidden.')
        except (OSError, ValueError):
            self.capture_failed = True
            self.status.setText('Capture mailbox unavailable.')

    def poll(self):
        if not self.nonce:
            if not self.capture_failed and self.stamp and time.time() - self.stamp > 5:
                self.status.setText('STALE — captured ' + datetime.fromtimestamp(self.stamp).strftime('%H:%M:%S') + '. Press Capture / Refresh for a new image.')
            return
        try:
            result = mirror_service.receive(self.root, self.nonce)
            if result is None:
                if time.monotonic() - self.started > 115: raise TimeoutError()
                return
            raw, stamp = result
            if sys.byteorder != 'little': raise ValueError('Unsupported pixel byte order')
            # Native RGB565 avoids a Python loop over 384,000 pixels on the UI thread.
            picture = QImage(raw, 800, 480, 1600, QImage.Format.Format_RGB16).copy()
            self.image.setPixmap(QPixmap.fromImage(picture))
            self.stamp = stamp
            self.capture_failed = False
            self.status.setText('Real device capture at ' + datetime.fromtimestamp(self.stamp).strftime('%H:%M:%S') + ' — image is read-only.')
        except (OSError, ValueError, RuntimeError, TimeoutError):
            self.capture_failed = True
            self.status.setText('Capture unavailable. Start the host, connect the display, leave permission/setup screens and retry. Existing image is STALE.')
        mirror_service.cancel(self.root, self.nonce)
        self.nonce = None; self.capture_button.setEnabled(True)

    def done(self, result):
        self.timer.stop()
        if self.nonce: mirror_service.cancel(self.root, self.nonce)
        self.nonce = None
        super().done(result)
