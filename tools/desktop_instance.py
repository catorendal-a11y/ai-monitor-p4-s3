"""One desktop window per installation; bounded local-only window activation."""
import hashlib
import os
from pathlib import Path

from PySide6.QtCore import QObject, QLockFile, QTimer, Signal
from PySide6.QtNetwork import QLocalServer, QLocalSocket

MESSAGES = {b'show\n': 'show', b'firmware\n': 'firmware'}


class DesktopInstance(QObject):
    requested = Signal(str)

    def __init__(self, root, parent=None):
        super().__init__(parent)
        root = Path(root).resolve()
        directory = root/'tools'; directory.mkdir(exist_ok=True)
        identity = str(root).casefold() if os.name == 'nt' else str(root)
        self.name = 'ai-monitor-ui-' + hashlib.sha256(identity.encode()).hexdigest()[:32]
        self.lock = QLockFile(str(directory/'aim_desktop.lock'))
        self.lock.setStaleLockTime(0)  # Never expire an active, long-running tray app.
        self.server = QLocalServer(self)
        self.server.setSocketOptions(QLocalServer.SocketOption.UserAccessOption)
        self.server.setMaxPendingConnections(4)
        self.server.newConnection.connect(self._accept)
        self.clients = set()

    def claim(self, firmware=False):
        if not self.lock.tryLock(0):
            if self.lock.error() != QLockFile.LockError.LockFailedError:
                raise RuntimeError('Use a writable installation folder to open AI Monitor.')
            socket = QLocalSocket()
            socket.connectToServer(self.name)
            if not socket.waitForConnected(1500):
                raise RuntimeError('AI Monitor is already opening. Wait a moment, then open it again or use its NOVA tray icon.')
            message = b'firmware\n' if firmware else b'show\n'
            socket.write(message)
            socket.flush()
            written = socket.waitForBytesWritten(1000) or socket.bytesToWrite() == 0
            socket.disconnectFromServer()
            if not written:
                raise RuntimeError('The existing window could not be reached. Use its NOVA tray icon.')
            return False
        # Only the lock owner may clean up its own stale local endpoint.
        QLocalServer.removeServer(self.name)
        if not self.server.listen(self.name):
            self.lock.unlock()
            raise RuntimeError('The local window could not start. Close AI Monitor and retry.')
        return True

    def _accept(self):
        while self.server.hasPendingConnections():
            socket = self.server.nextPendingConnection()
            if socket is None: continue
            if len(self.clients) >= 4:
                socket.abort(); socket.deleteLater(); continue
            self.clients.add(socket)
            socket.setReadBufferSize(16)
            pending = bytearray()
            timer = QTimer(socket); timer.setSingleShot(True); timer.setInterval(1500)
            timer.timeout.connect(socket.abort)
            def receive(socket=socket, pending=pending):
                pending.extend(bytes(socket.read(10)))
                if len(pending) > 9 or b'\n' in pending:
                    command = MESSAGES.get(bytes(pending))
                    if command: self.requested.emit(command)
                    socket.abort()
            def dispose(socket=socket):
                self.clients.discard(socket)
                socket.deleteLater()
            socket.readyRead.connect(receive)
            socket.disconnected.connect(dispose)
            timer.start()
            if socket.bytesAvailable(): receive()

    def close(self):
        for socket in tuple(self.clients): socket.abort()
        self.server.close()
        self.lock.unlock()
