"""Synthetic lifecycle and privacy regressions; no accounts or device writes."""
import contextlib
import io
import json
import os
import subprocess
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
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
from PySide6.QtWidgets import QApplication, QFileDialog
from desktop_window import MonitorWindow


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

    def test_lifecycle_failure_prints_no_exception_content(self):
        output=io.StringIO()
        with patch.dict(sys.modules,installation_lifecycle=types.SimpleNamespace(prepare=Mock(side_effect=RuntimeError('fixture-secret')))),contextlib.redirect_stdout(output):
            self.assertEqual(control.main(['--prepare-uninstall']),1)
        self.assertNotIn('fixture-secret',output.getvalue())

    def test_diagnostics_do_not_confirm_old_device_receipts_during_reconnect(self):
        from diagnostic_report import build
        from project_version import HOST_VERSION
        config={'board':'guition-p4','port':'COM6','providers':['codex']}
        health={'state':'connected','board':'guition-p4','port':'COM6','updated_at':100,
                'providers':{},'live':{'state':'acknowledged','updated_at':100,'agent_count':1},
                'hardware':{'firmwareVersion':HOST_VERSION},'hardware_at':100,
                'companion':{'state':'active','updated_at':100}}
        current=build(config,health,now=110)
        self.assertEqual(current['agent_usb']['state'],'acknowledged')
        self.assertEqual(current['firmware_version'],HOST_VERSION)
        self.assertEqual(current['companion_state'],'active')
        for disconnected in (True,False):
            health['state']='reconnecting' if disconnected else 'connected'
            if not disconnected:
                health['live']['updated_at']=health['hardware_at']=health['companion']['updated_at']=0
            report=build(config,health,now=110)
            self.assertEqual(report['agent_usb']['state'],'unconfirmed')
            self.assertIsNone(report['firmware_version'])
            self.assertEqual(report['companion_state'],'unconfirmed')

    def test_lifecycle_timeout_is_reported_without_command_or_output(self):
        output=io.StringIO()
        error=subprocess.TimeoutExpired(['fixture-secret'],12,output=b'fixture-secret')
        with patch.dict(sys.modules,installation_lifecycle=types.SimpleNamespace(prepare=Mock(side_effect=error))),contextlib.redirect_stdout(output):
            self.assertEqual(control.main(['--prepare-uninstall']),1)
        self.assertNotIn('fixture-secret',output.getvalue())

    def test_status_rejects_invalid_provider_timestamps(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);(root/'tools').mkdir()
            status=host_status.HostStatus(root/'tools');status.provider('codex','ready')
            self.assertIsNotNone(host_status.read_status(root,{os.getpid()}))
            for value in (True,float('nan'),-1,host_status.time.time()+60):
                status.data['provider_updated_at']['codex']=value
                (root/'tools/aim_host.status.json').write_text(json.dumps(status.data))
                self.assertIsNone(host_status.read_status(root,{os.getpid()}))


class Rc10UiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.app=QApplication.instance() or QApplication([])

    def setUp(self):
        self.directory=tempfile.TemporaryDirectory();self.addCleanup(self.directory.cleanup)
        self.root=Path(self.directory.name);self.window=MonitorWindow(self.root,monitor=False)
        self.addCleanup(self.finish)

    def finish(self):
        self.window.unsaved=False;self.window.config['keep_host_on_close']=True
        self.window.close();self.window.deleteLater();self.app.processEvents()

    def test_diagnostic_cancel_and_busy_do_not_export(self):
        with patch.object(QFileDialog,'getSaveFileName',return_value=('','')) as dialog,patch.object(self.window,'_run') as run:
            self.window.export_diagnostics();run.assert_not_called()
            self.window.busy=True;self.window.export_diagnostics()
            self.assertEqual(dialog.call_count,1)
            self.window.busy=False

    def test_diagnostic_action_writes_only_safe_metadata(self):
        target=self.root/'report.json'
        self.window.config['zai_key']='fixture-secret'
        with patch.object(QFileDialog,'getSaveFileName',return_value=(str(target),'')),patch.object(self.window,'_run') as run,patch.object(control,'owned_hosts',return_value=[]),patch('desktop_window.read_status',return_value=None):
            self.window.export_diagnostics()
            run.call_args.args[1](Mock())
        self.assertNotIn('fixture-secret',target.read_text())
        self.assertEqual(json.loads(target.read_text())['schema'],1)

    def test_clear_invalidates_existing_result_and_uses_worker(self):
        view=self.window.history_view;view.data={'old':True};generation=view.generation
        with patch.object(self.window,'_run') as run,patch.object(desktop,'clear_local_history') as clear:
            self.window.clear_history()
            self.assertGreater(view.generation,generation);self.assertIsNone(view.data)
            self.assertFalse(view.export_button.isEnabled())
            clear.assert_not_called()
            run.call_args.args[1](Mock());clear.assert_called_once()

if __name__=='__main__':unittest.main()
