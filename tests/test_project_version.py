"""Version parsing, generated resources and repository version agreement."""
import os
from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools'))
from project_version import (HOST_VERSION, fw_version, numeric_version,
                             version_tuple, windows_version_resource)


class ProjectVersionTests(unittest.TestCase):
    def write_config(self, text):
        directory = tempfile.TemporaryDirectory(); self.addCleanup(directory.cleanup)
        root = Path(directory.name)
        (root / 'src').mkdir()
        # BOM and CRLF are what Windows editors produce; parsing must tolerate both.
        (root / 'src' / 'config.h').write_bytes(b'\xef\xbb\xbf' + text.replace('\n', '\r\n').encode())
        return root

    def test_fw_version_parses_utf8_with_bom_and_surrounding_defines(self):
        root = self.write_config('#pragma once\n#define FW_VERSION "v1.18.3"\n#define OTHER "x"\n')
        self.assertEqual(fw_version(root), 'v1.18.3')

    def test_fw_version_accepts_prerelease_suffixes(self):
        root = self.write_config('#define FW_VERSION "v1.19.0-rc1"\n')
        self.assertEqual(fw_version(root), 'v1.19.0-rc1')
        self.assertEqual(numeric_version(fw_version(root)), '1.19.0-rc1')

    def test_missing_or_invalid_config_is_a_clear_error(self):
        with tempfile.TemporaryDirectory() as name:
            with self.assertRaises(ValueError) as caught: fw_version(Path(name))
            self.assertIn('src/config.h', str(caught.exception))
        root = self.write_config('#define FW_VERSION 3\n')
        with self.assertRaises(ValueError): fw_version(root)

    def test_version_tuple_ignores_suffix_and_rejects_garbage(self):
        self.assertEqual(version_tuple('v1.18.3'), (1, 18, 3))
        self.assertEqual(version_tuple('v2.0.0-beta.2'), (2, 0, 0))
        for value in ('1.18.3', 'v1.x.3', ''):
            with self.assertRaises(ValueError): version_tuple(value)

    def test_repository_versions_agree(self):
        # The drift guard for the release pipeline: firmware define, host-tool
        # constant and the top release-notes heading must name the same version.
        version = fw_version(ROOT)
        self.assertEqual(HOST_VERSION, version)
        from desktop_window import APP_VERSION
        self.assertEqual(APP_VERSION, version)
        heading = next((line.strip() for line in (ROOT / 'docs/RELEASE_NOTES.md').read_text(encoding='utf-8').splitlines()
                        if line.startswith('# AI Monitor v')), None)
        self.assertIsNotNone(heading, 'docs/RELEASE_NOTES.md must start with an "# AI Monitor vX.Y.Z" heading')
        self.assertEqual(heading, '# AI Monitor ' + version)

    def test_windows_version_resource_is_generated_from_the_version(self):
        resource = windows_version_resource('v1.18.3')
        self.assertIn('filevers=(1, 18, 3, 0)', resource)
        self.assertIn("'FileVersion', '1.18.3'", resource)
        self.assertIn("'ProductVersion', '1.18.3'", resource)
        self.assertNotIn('1.17.0', resource)
        # No stale hard-coded numbers: another version yields another resource.
        self.assertIn('filevers=(2, 0, 0, 0)', windows_version_resource('v2.0.0'))
        self.assertIn("'FileVersion', '2.0.0-rc1'", windows_version_resource('v2.0.0-rc1'))

    def test_release_builder_declares_the_shared_parser_and_generated_resource(self):
        script = (ROOT / 'scripts/build_windows_release.py').read_text(encoding='utf-8')
        self.assertIn('from project_version import HOST_VERSION, fw_version, windows_version_resource', script)
        self.assertIn('windows_version_resource(version)', script)
        self.assertNotIn("ROOT/'scripts/windows_version.txt'", script)
        self.assertFalse((ROOT / 'scripts/windows_version.txt').exists(),
                         'the hand-maintained version resource must stay deleted; it is generated now')

    def test_codex_handshake_uses_the_project_version(self):
        source = (ROOT / 'tools/codex_support.py').read_text(encoding='utf-8')
        self.assertIn('from project_version import HOST_VERSION, numeric_version', source)
        self.assertNotIn("'version':'1.", source)


if __name__ == '__main__':
    unittest.main()
