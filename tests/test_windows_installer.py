"""Installer consumes the reviewed package and retains private settings."""
import hashlib
import importlib.util
from pathlib import Path
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('installer_builder', ROOT/'scripts/build_windows_installer.py')
builder = importlib.util.module_from_spec(spec); spec.loader.exec_module(builder)


class InstallerTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory(); self.addCleanup(self.directory.cleanup)
        self.package = Path(self.directory.name)
        files = {'src/config.h': '#define FW_VERSION "v1.16.0"',
                 'AI-Monitor.exe': 'gui', 'AI-Monitor-Console.exe': 'host',
                 'AI-Monitor-Events.exe':'events', 'event-runtime/base_library.zip':'event runtime',
                 'firmware-flasher.exe': 'flasher', '_internal/PySide6/Qt6Core.dll': 'runtime'}
        for name, text in files.items():
            path = self.package/name; path.parent.mkdir(parents=True, exist_ok=True); path.write_text(text)
        self.hashes()

    def hashes(self):
        files = [path for path in self.package.rglob('*') if path.is_file() and path != self.package/'SHA256SUMS.txt']
        (self.package/'SHA256SUMS.txt').write_text('\n'.join(hashlib.sha256(path.read_bytes()).hexdigest()+'  '+
            path.relative_to(self.package).as_posix() for path in files))

    def test_complete_verified_package_is_accepted(self):
        self.assertEqual(builder.verify_package(self.package), '1.16.0')

    def test_prerelease_version_is_accepted_without_crashing(self):
        (self.package/'src/config.h').write_text('#define FW_VERSION "v1.17.0-rc1"')
        self.hashes()
        self.assertEqual(builder.verify_package(self.package), '1.17.0-rc1')

    def test_modified_missing_and_unreviewed_files_are_rejected(self):
        (self.package/'AI-Monitor.exe').write_text('changed')
        with self.assertRaises(ValueError): builder.verify_package(self.package)
        self.hashes(); (self.package/'extra.txt').write_text('unreviewed')
        with self.assertRaises(ValueError): builder.verify_package(self.package)
        (self.package/'extra.txt').unlink(); (self.package/'AI-Monitor-Console.exe').unlink(); self.hashes()
        with self.assertRaises(ValueError): builder.verify_package(self.package)

    def test_private_config_rejected_even_if_its_hash_is_added(self):
        path = self.package/'tools/aim_host.json'; path.parent.mkdir(); path.write_text('{}'); self.hashes()
        with self.assertRaises(ValueError): builder.verify_package(self.package)

    def test_checksum_path_cannot_escape_package(self):
        (self.package/'SHA256SUMS.txt').write_text('a'*64+'  ../outside.exe\n')
        with self.assertRaises(ValueError): builder.verify_package(self.package)

    def test_installer_preserves_config_and_requires_no_admin_or_security_bypass(self):
        script = (ROOT/'scripts/windows_installer.iss').read_text()
        self.assertIn('PrivilegesRequired=lowest', script)
        self.assertIn('DefaultDirName={localappdata}', script)
        self.assertIn('Excludes: "tools\\aim_host.json', script)
        self.assertNotIn('[UninstallDelete]', script)
        self.assertNotIn('powershell', script.lower())
        self.assertNotIn('unblock', script.lower())


if __name__ == '__main__': unittest.main()
