"""Isolated permission lifecycle: no real IPC endpoint, account, serial port or trust file."""
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import Mock, patch
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
import permission_runtime as module
from interaction_auth import TrustRecord
from permission_broker import TrustedContext
from permission_service import PermissionService
from aim_host import Panel


class PermissionRuntimeTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        (self.root / 'tools').mkdir()
        self.gate = Mock(return_value=False)
        self.runtime = module.PermissionRuntime(self.root, self.gate)
        self.addCleanup(self.runtime.close)
        self.store = patch.object(module, 'TrustStore').start()
        self.client_factory = patch.object(module, 'UsbPermissionClient').start()
        self.addCleanup(patch.stopall)
        self.store.return_value.load.return_value = TrustRecord('b'*32, bytes(range(1,33)))
        self.client = self.client_factory.return_value
        self.client.auth = object()
        self.panel = object()

    def enable(self):
        self.runtime.configure(True)
        self.gate.return_value = True
        return self.runtime.attach(self.panel)

    def test_default_and_local_gate_do_not_read_keys_or_create_service(self):
        self.assertFalse(self.runtime.attach(self.panel))
        self.runtime.configure(True)
        for gate in (False, 1, 'true', None):
            self.gate.return_value = gate
            self.assertFalse(self.runtime.attach(self.panel))
        self.store.assert_not_called()
        self.client_factory.assert_not_called()
        self.assertEqual(list((self.root/'tools').iterdir()), [])
        for value in (1, 'yes', None):
            with self.assertRaises(ValueError): self.runtime.configure(value)

    def test_one_existing_serial_owner_and_no_repeated_authentication(self):
        self.assertTrue(self.enable())
        self.assertTrue(self.runtime.attach(self.panel))
        self.client_factory.assert_called_once()
        args, kwargs = self.client_factory.call_args
        self.assertIs(args[0], self.panel)
        self.assertTrue(kwargs['opted_in'])
        self.client.open.assert_called_once()
        self.assertEqual(self.runtime.state, 'connected')
        self.runtime.pump()
        self.client.pump.assert_called_once()

    def test_ambiguous_start_not_retried_on_same_connection(self):
        self.client.open.side_effect = TimeoutError('fixture-secret-not-for-status')
        self.assertFalse(self.enable())
        self.assertFalse(self.runtime.attach(self.panel))
        self.client.open.assert_called_once()
        self.client.close.assert_called_once()
        self.assertEqual(self.runtime.state, 'unavailable')
        self.assertNotIn('fixture-secret', self.runtime.state)
        self.client.open.side_effect = None
        self.assertTrue(self.runtime.attach(object()))
        self.assertEqual(self.client.open.call_count, 2)

    def test_missing_enrollment_does_not_open_authenticated_channel(self):
        self.store.return_value.load.return_value = None
        self.assertFalse(self.enable())
        self.assertEqual(self.runtime.state, 'not_enrolled')
        self.client_factory.assert_not_called()

    def test_opt_out_or_local_validation_loss_cancels_immediately(self):
        for opt_out in (True, False):
            self.panel = object()
            self.assertTrue(self.enable())
            if opt_out: self.runtime.configure(False)
            else:
                self.gate.return_value = False
                self.runtime.pump()
            self.assertIsNone(self.runtime.client)
            self.assertIsNone(self.runtime.panel)
        self.assertEqual(self.client.close.call_count, 2)

    def test_synchronous_packets_are_not_swallowed_by_panel_dispatch(self):
        self.assertTrue(self.enable())
        message = dict(type='interaction_packet', fixture='no-real-permission')
        self.client.handle_event.return_value = False
        panel = object.__new__(Panel)
        panel.permission_runtime = self.runtime
        self.assertFalse(panel.handle_event(message))
        self.client.handle_event.return_value = True
        self.assertTrue(panel.handle_event(message))
        self.runtime.close()
        self.assertTrue(panel.handle_event(message))  # Closed session discards stale packets.

    def test_usb_failure_closes_service_and_does_not_restart_it(self):
        self.assertTrue(self.enable())
        self.client.pump.side_effect = lambda: setattr(self.client, 'auth', None)
        self.runtime.pump()
        self.assertIsNone(self.runtime.client)
        self.assertFalse(self.runtime.attach(self.panel))
        self.client.close.assert_called_once()

    def test_replay_ledger_survives_service_and_usb_replacement(self):
        self.assertTrue(self.enable())
        _, kwargs = self.client_factory.call_args
        context = TrustedContext(True, True, self.runtime.instance, 'b'*32, 'c'*64, True)
        first = kwargs['service_factory'](context)
        self.assertIs(first.broker, self.runtime.broker)
        request = dict(schema=1, instance=self.runtime.instance, requestId='d'*32, nonce='e'*64,
                       revision=1, tool='Read', hint='{"file_path":"fixture.txt"}', expiresInMs=1000)
        first.broker.submit(request)
        first.close()
        second_context = TrustedContext(True, True, self.runtime.instance, 'b'*32, 'f'*64, True)
        second = PermissionService(self.root, second_context, broker=self.runtime.broker)
        self.addCleanup(second.close)
        with self.assertRaises(ValueError): second.broker.submit(request)
        with self.assertRaises(ValueError): second.broker.submit(dict(request, requestId='f'*32))

    def test_panel_close_always_closes_serial_after_permission_shutdown(self):
        panel = object.__new__(Panel)
        panel.permission_runtime = Mock(close=Mock(side_effect=RuntimeError('fixture')))
        panel.ser = Mock()
        with self.assertRaises(RuntimeError): panel.close()
        panel.ser.close.assert_called_once()

    def test_panel_attachment_requires_local_runtime_and_uses_existing_owner(self):
        panel = object.__new__(Panel)
        panel.permission_runtime = None
        with self.assertRaises(ValueError): panel.attach_permission_runtime({'trusted': True})
        self.runtime.configure(True);self.gate.return_value = True
        self.assertTrue(panel.attach_permission_runtime(self.runtime))
        self.assertIs(self.client_factory.call_args.args[0], panel)
        self.assertIs(panel.permission_runtime, self.runtime)

    def test_failed_service_shutdown_blocks_replacement_until_host_restart(self):
        self.assertTrue(self.enable())
        self.client.shutdown_complete = False
        self.runtime.close()
        self.assertFalse(self.runtime.attach(object()))
        self.runtime.configure(False);self.runtime.configure(True)
        self.assertFalse(self.runtime.attach(object()))
        self.client.open.assert_called_once()

    def test_failed_shutdown_during_direct_panel_replacement_cannot_start_new_service(self):
        self.assertTrue(self.enable())
        self.client.shutdown_complete = False
        self.assertFalse(self.runtime.attach(object()))
        self.client.open.assert_called_once()


if __name__ == '__main__': unittest.main()
