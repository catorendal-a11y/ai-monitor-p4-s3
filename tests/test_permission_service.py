"""Local permission service fixtures; no production endpoint, hook or USB decision."""
from dataclasses import replace
import os
from pathlib import Path
import secrets
import sys
import tempfile
import threading
import time
import unittest
from unittest.mock import Mock, patch
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
import permission_service as service
from permission_broker import TrustedContext
from permission_ipc import Listener, connect


class PermissionServiceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name); (self.root / 'tools').mkdir()
        self.context = TrustedContext(True, True, 'a' * 32, 'b' * 32, 'c' * 64, True)
        self.message = dict(schema=1, instance='a' * 32, requestId='d' * 32, nonce='e' * 64,
                            revision=1, tool='Read', hint='{"file_path":"fixture.txt"}', expiresInMs=25000)
        self.server = service.PermissionService(self.root, self.context)

    def test_untrusted_start_and_wrong_process_refused(self):
        with self.assertRaises(ValueError): service.PermissionService(self.root, TrustedContext())
        with self.assertRaises(ValueError): self.server.start()
        self.assertFalse((self.root / 'tools/permission-endpoint.json').exists())

    def test_wrong_helper_cannot_submit_or_receive(self):
        channel = Mock(); channel.peer_pid.return_value = 123
        with patch.object(service, 'verified_helper', return_value=False): self.server._serve(channel)
        channel.receive.assert_not_called(); channel.send.assert_not_called()
        channel.close.assert_called_once(); self.assertIsNone(self.server.broker.current())

    def test_endpoint_cleanup_preserves_other_host_instance(self):
        self.server._publish_endpoint()
        self.server.update_context(replace(self.context, connected=False))
        self.server._remove_endpoint()
        path = self.root / 'tools/permission-endpoint.json'
        self.assertFalse(path.exists())
        path.write_text('{"schema":1,"pid":123,"instance":"other"}')
        self.server._remove_endpoint(); self.assertTrue(path.exists())
        self.assertNotIn('hint', path.read_text())

    def test_changed_context_after_device_decision_cancels_before_send(self):
        channel = Mock(); channel.peer_pid.return_value = os.getpid()
        channel.receive.return_value = self.message
        def wait(_):
            self.server.resolve('d' * 32, 'e' * 64, 1, 'allow', self.context)
            self.server.update_context(replace(self.context, connected=False))
        with patch.object(service, 'verified_helper', return_value=True), patch.object(self.server._wake, 'wait', side_effect=wait):
            self.server._serve(channel)
        channel.send.assert_not_called(); channel.close.assert_called_once()

    @unittest.skipUnless(os.name == 'nt', 'Windows named pipes')
    def test_helper_disconnect_cancels_pending_request(self):
        name = 'ai-monitor-permission-' + secrets.token_hex(16)
        listener = Listener(name); self.addCleanup(listener.close)
        errors = []
        def serve():
            try: self.server._serve(listener.accept(2))
            except BaseException as error: errors.append(error)
        with patch.object(service, 'verified_helper', return_value=True):
            thread = threading.Thread(target=serve); thread.start()
            channel = connect(name)
            try:
                channel.send(self.message)
                deadline = time.monotonic() + 2
                while self.server.broker.current() is None and time.monotonic() < deadline:
                    time.sleep(.005)
                self.assertIsNotNone(self.server.broker.current())
            finally: channel.close()
            thread.join(2)
            self.server.close()
        self.assertFalse(thread.is_alive()); self.assertEqual(errors, [])
        self.assertIsNone(self.server.broker.current())
        with self.assertRaises(ValueError):
            self.server.resolve('d' * 32, 'e' * 64, 1, 'allow', self.context)

    @unittest.skipUnless(os.name == 'nt', 'Windows named pipes')
    def test_listener_survives_idle_timeout_and_stops_cleanly(self):
        with patch.object(service.psutil, 'Process', return_value=Mock(exe=Mock(return_value=str(self.root / 'AI-Monitor-Console.exe')))), \
                patch.object(service, 'verified_helper', return_value=True):
            self.server.start()
            try:
                time.sleep(.35)  # Exercise cancel/re-arm after an idle accept deadline.
                channel = connect(service.pipe_name(self.root))
                try:
                    channel.send(self.message)
                    deadline = time.monotonic() + 2
                    while self.server.broker.current() is None and time.monotonic() < deadline:
                        time.sleep(.005)
                    self.assertIsNotNone(self.server.broker.current())
                    self.server.resolve('d' * 32, 'e' * 64, 1, 'deny', self.context)
                    self.assertEqual(channel.receive(2)['decision'], 'deny')
                finally: channel.close()
            finally: self.server.close()
        self.assertFalse(self.server._thread.is_alive())
        self.assertFalse((self.root / 'tools/permission-endpoint.json').exists())

    @unittest.skipUnless(os.name == 'nt', 'Windows named pipes')
    def test_real_local_roundtrip_with_fixture_decision(self):
        name = 'ai-monitor-permission-' + secrets.token_hex(16)
        listener = Listener(name); self.addCleanup(listener.close)
        errors = []
        def serve():
            try: self.server._serve(listener.accept(2))
            except BaseException as error: errors.append(error)
        with patch.object(service, 'verified_helper', return_value=True):
            thread = threading.Thread(target=serve); thread.start()
            channel = connect(name)
            try:
                channel.send(self.message)
                deadline = time.monotonic() + 2
                while self.server.broker.current() is None and time.monotonic() < deadline:
                    time.sleep(.005)
                self.assertIsNotNone(self.server.broker.current())
                self.server.resolve('d' * 32, 'e' * 64, 1, 'deny', self.context)
                response = channel.receive(2)
                self.assertEqual(response['decision'], 'deny')
                self.assertEqual(response['nonce'], 'e' * 64)
                self.assertNotIn('hint', response)
            finally:
                self.server.close(); channel.close(); thread.join(3)
        self.assertFalse(thread.is_alive()); self.assertEqual(errors, [])


if __name__ == '__main__': unittest.main()
