"""Synthetic PC connection lifecycle. No serial port, NVS, host process or real trust file."""
from pathlib import Path
import sys
import unittest
from unittest.mock import Mock, patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
import enrollment_setup as setup

class EnrollmentSetupTests(unittest.TestCase):
    def test_comparison_defaults_to_cancel_and_cannot_be_changed_after_decision(self):
        prompt=setup.ComparisonPrompt('AAAA-BBBB-CCCC-DDDD')
        self.assertFalse(prompt.wait(0));prompt.decide(True);self.assertFalse(prompt.wait(0))
        prompt=setup.ComparisonPrompt('AAAA-BBBB-CCCC-DDDD');prompt.decide(True)
        self.assertTrue(prompt.wait(0));prompt.decide(False);self.assertTrue(prompt.wait(0))
        for value in (1,'yes',None):
            prompt=setup.ComparisonPrompt('AAAA-BBBB-CCCC-DDDD');prompt.decide(value);self.assertFalse(prompt.wait(0))

    def test_scoped_host_pause_and_restore_close_the_single_serial_owner(self):
        for accepted in (False,True):
            panel=Mock();client=Mock();client.begin.return_value='AAAA-BBBB-CCCC-DDDD'
            with patch.object(setup.control,'local_config',return_value=dict(board='guition-p4',port='COM6')), \
                 patch.object(setup.control,'owned_hosts',side_effect=[[Mock()],[]]), \
                 patch.object(setup.control,'stop_host') as stop,patch.object(setup.control,'start_host') as start, \
                 patch.object(setup.control.host,'Panel',return_value=panel) as create, \
                 patch.object(setup,'TrustStore'),patch.object(setup,'UsbEnrollmentClient',return_value=client), \
                 patch.object(setup.time,'sleep'):
                if accepted:setup.connect_device(Path('.'),lambda prompt:prompt.decide(True),Mock())
                else:
                    with self.assertRaises(setup.control.SetupError):setup.connect_device(Path('.'),lambda prompt:prompt.decide(False),Mock())
                stop.assert_called_once();start.assert_called_once();create.assert_called_once_with('COM6')
                panel.close.assert_called_once();client.close.assert_called_once()
                self.assertEqual(client.finish.call_count,int(accepted))

    def test_a_host_that_did_not_stop_never_opens_serial(self):
        with patch.object(setup.control,'local_config',return_value=dict(board='guition-p4',port='COM6')), \
             patch.object(setup.control,'owned_hosts',side_effect=[[Mock()],[Mock()]]), \
             patch.object(setup.control,'stop_host'),patch.object(setup.control,'start_host'), \
             patch.object(setup.control.host,'Panel') as create:
            with self.assertRaises(setup.control.SetupError):setup.connect_device(Path('.'),Mock(),Mock())
            create.assert_not_called()

    def test_failure_restores_running_host_and_leaves_stopped_host_stopped(self):
        for running in (False,True):
            panel=Mock();panel.heartbeat.side_effect=RuntimeError('Synthetic identity mismatch')
            with patch.object(setup.control,'local_config',return_value=dict(board='guition-p4',port='COM6')), \
                 patch.object(setup.control,'owned_hosts',side_effect=[[Mock()] if running else [],[]]), \
                 patch.object(setup.control,'stop_host'),patch.object(setup.control,'start_host') as start, \
                 patch.object(setup.control.host,'Panel',return_value=panel),patch.object(setup.time,'sleep'):
                with self.assertRaises(setup.control.SetupError):setup.connect_device(Path('.'),Mock(),Mock())
                self.assertEqual(start.call_count,int(running));panel.close.assert_called_once()
