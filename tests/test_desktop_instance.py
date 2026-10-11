"""Local window handoff accepts fixed display commands, never host/file commands."""
import os
from pathlib import Path
import sys
import subprocess
import time
import tempfile
import unittest

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
from PySide6.QtWidgets import QApplication
from PySide6.QtNetwork import QLocalServer, QLocalSocket
from PySide6.QtTest import QTest
from desktop_instance import DesktopInstance


class InstanceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls): cls.application=QApplication.instance() or QApplication([])

    def setUp(self):
        self.directory=tempfile.TemporaryDirectory(); self.addCleanup(self.directory.cleanup)
        self.root=Path(self.directory.name)
        self.owner=DesktopInstance(self.root); self.assertTrue(self.owner.claim())
        self.addCleanup(self.owner.close)
        self.commands=[]; self.owner.requested.connect(self.commands.append)

    def send(self, message):
        socket=QLocalSocket(); socket.connectToServer(self.owner.name)
        self.assertTrue(socket.waitForConnected(1000))
        socket.write(message); socket.waitForBytesWritten(1000)
        QTest.qWait(35)
        socket.abort()
        QTest.qWait(10)

    def test_second_launch_reuses_owner_and_can_open_firmware(self):
        # The existing GUI must continue processing connections while the new
        # process performs its bounded startup handoff.
        script = ('import sys; from PySide6.QtCore import QCoreApplication; '
                  'from desktop_instance import DesktopInstance; '
                  'app=QCoreApplication([]); i=DesktopInstance(sys.argv[1]); '
                  'assert i.claim(firmware=True) is False')
        environment=dict(os.environ)
        environment['PYTHONPATH']=str(Path(__file__).resolve().parents[1]/'tools')
        process=subprocess.Popen([sys.executable,'-c',script,str(self.root)],env=environment,
            stdout=subprocess.PIPE,stderr=subprocess.PIPE)
        deadline=time.monotonic()+8
        while process.poll() is None and time.monotonic()<deadline: QTest.qWait(20)
        if process.poll() is None: process.kill()
        stdout,stderr=process.communicate(timeout=3)
        self.assertEqual(process.returncode,0,stderr.decode(errors='replace'))
        QTest.qWait(35)
        self.assertEqual(self.commands,['firmware'])
        self.assertTrue(self.owner.lock.isLocked())

    def test_only_fixed_window_commands_are_accepted(self):
        for raw in (b'start_host\n',b'exec\n',b'../../auth.json\n',b'show\nquit\n',b'x'*1000):
            self.send(raw)
        self.assertEqual(self.commands,[])
        self.send(b'show\n'); self.assertEqual(self.commands,['show'])
        self.assertEqual(self.owner.server.socketOptions(),QLocalServer.SocketOption.UserAccessOption)

    def test_closed_owner_releases_lock_for_next_launch(self):
        self.owner.close()
        replacement=DesktopInstance(self.root); self.addCleanup(replacement.close)
        self.assertTrue(replacement.claim())

    def test_fragmented_show_command_waits_for_complete_line(self):
        socket = QLocalSocket(); socket.connectToServer(self.owner.name)
        self.assertTrue(socket.waitForConnected(1000))
        socket.write(b'sho'); socket.flush(); QTest.qWait(35)
        self.assertEqual(self.commands, [])
        socket.write(b'w\n'); socket.flush(); QTest.qWait(35)
        self.assertEqual(self.commands, ['show'])
        socket.abort(); QTest.qWait(10)

    def test_separate_installations_do_not_share_window_ownership(self):
        other=self.root/'other'; other.mkdir()
        second=DesktopInstance(other); self.addCleanup(second.close)
        self.assertTrue(second.claim()); self.assertNotEqual(second.name,self.owner.name)


if __name__=='__main__': unittest.main()
