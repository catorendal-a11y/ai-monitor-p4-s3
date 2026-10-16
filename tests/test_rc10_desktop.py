"""Synthetic lifecycle and privacy regressions; no accounts or device writes."""
import contextlib
import io
from pathlib import Path
import sys
import tempfile
import types
import unittest
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
import aim_control as control
import desktop_support as desktop
import host_status


class Rc10Tests(unittest.TestCase):
    def test_lifecycle_cli_precedes_configuration(self):
        prepare=Mock()
        with tempfile.TemporaryDirectory() as directory, patch.dict(sys.modules, installation_lifecycle=types.SimpleNamespace(prepare=prepare)), patch.object(control,'local_config',side_effect=AssertionError('private configuration')):
            self.assertEqual(control.main(['--prepare-upgrade','--installation-root',directory]),0)
            prepare.assert_called_once_with(Path(directory).resolve(),uninstall=False)

    def test_lifecycle_root_requires_lifecycle_action(self):
        with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
            control.main(['--check','--installation-root','C:/example'])

    def test_clear_restores_running_host_and_never_clears_after_failed_stop(self):
        for running in (False,True):
            calls=[]
            with patch.object(control,'owned_hosts',return_value=[Mock()] if running else []), patch.object(control,'stop_host',side_effect=lambda *a,**k:calls.append('stop')), patch.object(control,'start_host',side_effect=lambda *a,**k:calls.append('start')), patch('usage_history.clear_history',side_effect=lambda *a:calls.append('clear')):
                desktop.clear_local_history(Path('fixture'),Mock())
            self.assertEqual(calls,['stop','clear','start'] if running else ['stop','clear'])
        with patch.object(control,'owned_hosts',return_value=[Mock()]), patch.object(control,'stop_host',side_effect=RuntimeError('stop')), patch.object(control,'start_host') as start, patch('usage_history.clear_history') as clear:
            with self.assertRaises(RuntimeError): desktop.clear_local_history(Path('fixture'),Mock())
            clear.assert_not_called();start.assert_not_called()

    def test_clear_failure_restores_prior_running_host(self):
        with patch.object(control,'owned_hosts',return_value=[Mock()]),patch.object(control,'stop_host'),patch.object(control,'start_host') as start,patch('usage_history.clear_history',side_effect=ValueError('database')):
            with self.assertRaises(ValueError):desktop.clear_local_history(Path('fixture'),Mock())
            start.assert_called_once()

    def test_provider_check_and_success_timestamps_are_independent(self):
        with tempfile.TemporaryDirectory() as directory:
            status=host_status.HostStatus(directory)
            with patch.object(host_status.time,'time',return_value=100):status.provider('codex','ready')
            with patch.object(host_status.time,'time',return_value=110):status.provider('codex','unavailable')
            self.assertEqual(status.data['provider_updated_at']['codex'],110)
            self.assertEqual(status.data['provider_success_at']['codex'],100)

    def test_diagnostics_are_whitelisted_and_stale_health_is_unconfirmed(self):
        from diagnostic_report import build, provider_health_text
        config={'board':'guition-p4','port':'COM6','providers':['codex','claude'],'zai_key':'fixture-secret'}
        health={'state':'connected','board':'guition-p4','port':'COM6','updated_at':100,'providers':{'codex':'ready','claude':'activity_only'},'provider_updated_at':{'codex':99},'provider_success_at':{'codex':98},'error':'fixture-secret','tool_args':'fixture-secret','hardware':{'firmwareVersion':'fixture-secret'}}
        report=build(config,health,now=110)
        self.assertNotIn('fixture-secret',str(report))
        self.assertEqual(report['providers']['codex']['checked_age_s'],11)
        self.assertFalse(report['physical_permissions_enabled'])
        self.assertIn('quota received',provider_health_text(config,health,now=110))
        self.assertNotIn('quota received',provider_health_text(config,health,now=200))
        health['board']='esp32s3-waveshare-43'
        self.assertFalse(build(config,health,now=110)['host']['confirmed'])

if __name__=='__main__':unittest.main()
