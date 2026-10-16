"""Regression paths use only temporary homes/config and injected read failures."""
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
import aim_host as host
import provider_setup as setup
import claude_permission_setup
from token_activity import TokenReporter

class ClaudeRootTests(unittest.TestCase):
    def test_alternate_profile_receives_links_and_readers_without_touching_default(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d)/'app';root.mkdir()
            home=Path(d)/'home';home.mkdir()
            alternate=Path(d)/'alternate';alternate.mkdir()
            settings=alternate/'settings.json';settings.write_text('{"theme":"dark"}')
            with patch.object(Path,'home',return_value=home),patch.dict(os.environ,{'CLAUDE_CONFIG_DIR':str(alternate)}):
                setup.claude_session_link(root)
                self.assertTrue(settings.exists())
                self.assertIn('hooks',json.loads(settings.read_text()))
                self.assertEqual(setup.claude_session_state(root),'installed')
                setup.claude_bridge(root)
                self.assertEqual(setup.claude_link_state(root),'installed')
                self.assertEqual(TokenReporter(providers=['claude']).paths['claude'],alternate/'projects')
                self.assertEqual(claude_permission_setup.settings_path(),settings)
                setup.claude_bridge(root,remove=True)
                setup.claude_session_link(root,remove=True)
                self.assertNotIn('statusLine',json.loads(settings.read_text()))
                self.assertEqual(json.loads(settings.read_text())['theme'],'dark')
                self.assertFalse((home/'.claude').exists())

    def test_explicit_test_home_is_isolated_from_environment_and_empty_override_defaults(self):
        with tempfile.TemporaryDirectory() as d:
            home=Path(d)/'home';home.mkdir();other=Path(d)/'other'
            with patch.dict(os.environ,{'CLAUDE_CONFIG_DIR':str(other)}):
                setup.claude_session_link(home,home=home)
                self.assertTrue((home/'.claude/settings.json').exists())
                self.assertEqual(TokenReporter(home=home,providers=['claude']).paths['claude'],home/'.claude/projects')
                self.assertFalse(other.exists())
            with patch.object(Path,'home',return_value=home),patch.dict(os.environ,{'CLAUDE_CONFIG_DIR':''}):
                self.assertEqual(claude_permission_setup.settings_path(),home/'.claude/settings.json')

class ConfigRetryTests(unittest.TestCase):
    def watcher(self):
        with patch.object(host.ConfigWatcher,'fingerprint',return_value=('old',1)):
            return host.ConfigWatcher()

    def test_transient_failed_read_retries_without_another_save_and_with_backoff(self):
        watcher=self.watcher();config={'port':'COM9999'}
        with patch.object(host.ConfigWatcher,'fingerprint',return_value=('new',2)),patch.object(host,'load_config',side_effect=[PermissionError(),config]) as load,patch.object(host,'LOG'),patch.object(host.time,'monotonic',return_value=0) as clock:
            watcher.check();self.assertIsNone(watcher.take())
            self.assertEqual(watcher.signature,('old',1))
            clock.return_value=1;watcher.check();self.assertEqual(load.call_count,1)
            clock.return_value=2;watcher.check();self.assertEqual(watcher.take(),config)
            watcher.check();self.assertEqual(load.call_count,2)

    def test_new_save_bypasses_old_failure_backoff_and_invalid_files_retry_bounded(self):
        watcher=self.watcher()
        with patch.object(host.ConfigWatcher,'fingerprint',return_value=('bad',2)) as fingerprint,patch.object(host,'load_config',side_effect=[ValueError(),ValueError(),{'port':'COM9999'}]) as load,patch.object(host,'LOG') as log,patch.object(host.time,'monotonic',return_value=0) as clock:
            watcher.check();clock.return_value=1;watcher.check();self.assertEqual(load.call_count,1)
            clock.return_value=2;watcher.check();self.assertEqual(load.call_count,2)
            fingerprint.return_value=('corrected',3);watcher.check()
            self.assertEqual(watcher.take(),{'port':'COM9999'});self.assertEqual(log.call_count,2)
