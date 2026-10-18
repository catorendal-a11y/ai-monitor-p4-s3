"""Repository permissions must stay separate from code/dependency execution."""
from pathlib import Path
import unittest

try:
    import yaml
except ImportError:
    yaml = None

ROOT = Path(__file__).resolve().parents[1]


@unittest.skipIf(yaml is None, 'Install scripts/requirements-test.txt for workflow security tests')
class WorkflowSecurityTests(unittest.TestCase):
    def workflows(self):
        return [(path, yaml.safe_load(path.read_text())) for path in (ROOT / '.github/workflows').glob('*.yml')]

    def test_actions_are_pinned_and_checkout_does_not_store_credentials(self):
        for path, document in self.workflows():
            for job in document['jobs'].values():
                self.assertNotIn('self-hosted', str(job['runs-on']), path.name)
                for step in job['steps']:
                    action = step.get('uses')
                    if not action: continue
                    self.assertRegex(action, r'^actions/[a-z-]+@[a-f0-9]{40}$')
                    if action.startswith('actions/checkout@'):
                        self.assertIs(step.get('with', {}).get('persist-credentials'), False)

    def test_only_isolated_publisher_has_write_permission(self):
        for path, document in self.workflows():
            self.assertEqual(document['permissions'], {'contents': 'read'})
            for name, job in document['jobs'].items():
                permissions = job.get('permissions', document['permissions'])
                if 'write' not in permissions.values(): continue
                self.assertEqual((path.name, name), ('release.yml', 'publish'))
                self.assertEqual(permissions, {'actions': 'read', 'contents': 'write',
                                              'id-token': 'write', 'attestations': 'write'})
                self.assertEqual(job['needs'], 'windows')
                for step in job['steps']:
                    if step.get('uses'):
                        self.assertTrue(step['uses'].startswith(('actions/download-artifact@', 'actions/attest-build-provenance@')))
                        if step['uses'].startswith('actions/attest-build-provenance@'):
                            self.assertNotIn('run', step)
                            subjects = step['with']['subject-path']
                            self.assertIn('work/publish/', subjects)
                            self.assertNotIn('work/publish/work/terminal-release/', subjects)
                            self.assertNotIn('${{', subjects)
                    script = step.get('run', '')
                    self.assertNotRegex(script, r'(?i)python|pip install|\.exe|checkout|Invoke-Expression')
                    if 'gh release create' in script:
                        self.assertIn('--draft', script)
                        self.assertIn('--verify-tag', script)

    def test_firmware_downloads_preserve_board_directories(self):
        document=yaml.safe_load((ROOT/'.github/workflows/release.yml').read_text())
        downloads=[step['with'] for step in document['jobs']['windows']['steps'] if step.get('uses','').startswith('actions/download-artifact@')]
        for board in ('guition-p4','waveshare-s3-43'):
            self.assertIn({'name':'firmware-'+board,'path':'work/prebuilt/'+board},downloads,
                          'Equal firmware filenames from different boards must never be merged')

    def test_release_smokes_fresh_archive_and_publishes_only_current_notes(self):
        raw=(ROOT/'.github/workflows/release.yml').read_text()
        self.assertIn('Expand-Archive',raw)
        self.assertIn('RELEASE_NOTES-current.md',raw)
        self.assertIn("$taskFolder = 'work/publish'",raw)
        self.assertNotIn("$taskFolder = 'work/publish/work/terminal-release'",raw)
        self.assertNotIn('--notes-file work/publish/docs/RELEASE_NOTES.md',raw)

    def test_external_events_do_not_get_privileged_context_or_named_secrets(self):
        for path, document in self.workflows():
            raw = path.read_text()
            self.assertNotIn('pull_request_target', raw)
            self.assertNotIn('secrets.', raw)
            if path.name == 'release.yml':
                # PyYAML 1.1 recognizes "on" as a boolean key.
                triggers = document.get('on', document.get(True))
                self.assertEqual(triggers, {'push': {'tags': ['v*']}})
