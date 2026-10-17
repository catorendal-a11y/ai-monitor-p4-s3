"""Installer consumes the reviewed package and retains private settings."""
import hashlib
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('installer_builder', ROOT/'scripts/build_windows_installer.py')
builder = importlib.util.module_from_spec(spec); spec.loader.exec_module(builder)
from test_board_profiles import images
from board_profiles import BOARDS


class InstallerTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory(); self.addCleanup(self.directory.cleanup)
        self.package = Path(self.directory.name)
        files = {'src/config.h': '#define FW_VERSION "v1.16.0"',
                 'AI-Monitor.exe': 'gui', 'AI-Monitor-Console.exe': 'host',
                 'AI-Monitor-Events.exe':'events', 'event-runtime/base_library.zip':'event runtime',
                 'AI-Monitor-Permission.exe': 'permission', 'permission-runtime/base_library.zip': 'permission runtime',
                 '_internal/base_library.zip': 'gui runtime',
                 'firmware-flasher.exe': 'flasher', '_internal/PySide6/Qt6Core.dll': 'runtime',
                 'AI-Monitor-Terminal.bat':'terminal launcher', 'setup.ps1':'setup',
                 'tools/aim_terminal.py':'terminal', 'tools/terminal_art.py':'art',
                 'tools/requirements.txt':'dependencies', 'assets/terminal/nova.json':'pixels',
                 'docs/TERMINAL.md':'terminal guide','Install-Nova.ps1':'command installer',
                 'terminal-bin/nova.cmd':'terminal command'}
        for name, text in files.items():
            path = self.package/name; path.parent.mkdir(parents=True, exist_ok=True); path.write_text(text)
        self.records = {key: images(self.package, key) for key in BOARDS}
        self.firmware('v1.16.0')
        self.hashes()

    def firmware(self, version):
        for key, record in self.records.items():
            folder = self.package/'firmware'/key
            app = (folder/'application.bin').read_bytes()[:24] + b'synthetic-application ' + version.encode()
            factory = (folder/'factory.bin').read_bytes()[:0x10000] + app
            for name, data in [('application.bin', app), ('factory.bin', factory)]:
                (folder/name).write_bytes(data)
                record['files'][name].update(sha256=hashlib.sha256(data).hexdigest(), bytes=len(data))
        (self.package/'firmware/manifest.json').write_text(json.dumps(
            {'schema': 2, 'version': version, 'boards': self.records}))

    def hashes(self):
        files = [path for path in self.package.rglob('*') if path.is_file() and path != self.package/'SHA256SUMS.txt']
        (self.package/'SHA256SUMS.txt').write_text('\n'.join(hashlib.sha256(path.read_bytes()).hexdigest()+'  '+
            path.relative_to(self.package).as_posix() for path in files))

    def test_complete_verified_package_is_accepted(self):
        self.assertEqual(builder.verify_package(self.package), '1.16.0')

    def test_prerelease_version_is_accepted_without_crashing(self):
        (self.package/'src/config.h').write_text('#define FW_VERSION "v1.17.0-rc1"')
        self.firmware('v1.17.0-rc1')
        self.hashes()
        self.assertEqual(builder.verify_package(self.package), '1.17.0-rc1')

    def test_missing_components_rejected_even_with_updated_checksums(self):
        names = ['AI-Monitor-Permission.exe', 'permission-runtime/base_library.zip',
                 '_internal/base_library.zip', 'event-runtime/base_library.zip', 'firmware/manifest.json']
        names += ['firmware/'+key+'/'+name for key in BOARDS for name in ('application.bin', 'factory.bin')]
        names += ['AI-Monitor-Terminal.bat','setup.ps1','tools/aim_terminal.py','tools/terminal_art.py',
                  'tools/requirements.txt','assets/terminal/nova.json','docs/TERMINAL.md',
                  'Install-Nova.ps1','terminal-bin/nova.cmd']
        for name in names:
            with self.subTest(component=name):
                path = self.package/name; data = path.read_bytes(); path.unlink(); self.hashes()
                with self.assertRaises((ValueError, OSError)): builder.verify_package(self.package)
                path.write_bytes(data); self.hashes()

    def test_wrong_firmware_version_and_board_rejected_even_with_updated_checksums(self):
        manifest = self.package/'firmware/manifest.json'
        for change in ('version', 'schema', 'board', 'chip', 'offset'):
            with self.subTest(change=change):
                self.firmware('v1.16.0')
                data = json.loads(manifest.read_text())
                record = data['boards']['guition-p4']
                if change == 'version': data['version'] = 'v1.15.0'
                elif change == 'schema': data['schema'] = 1
                elif change == 'offset': record['files']['application.bin']['offset'] = 0
                else: record[change] = 'wrong'
                manifest.write_text(json.dumps(data)); self.hashes()
                with self.assertRaises(ValueError): builder.verify_package(self.package)

    def test_wrong_image_version_and_factory_layout_rejected_with_updated_hashes(self):
        self.firmware('v1.15.0')
        manifest = self.package/'firmware/manifest.json'
        data = json.loads(manifest.read_text()); data['version'] = 'v1.16.0'
        manifest.write_text(json.dumps(data)); self.hashes()
        with self.assertRaises(ValueError): builder.verify_package(self.package)
        self.firmware('v1.16.0')
        path = self.package/'firmware/guition-p4/factory.bin'
        raw = bytearray(path.read_bytes()); raw[0x2003] = 0x2f; path.write_bytes(raw)
        self.records['guition-p4']['files']['factory.bin']['sha256'] = hashlib.sha256(raw).hexdigest()
        manifest.write_text(json.dumps({'schema': 2, 'version': 'v1.16.0', 'boards': self.records})); self.hashes()
        with self.assertRaises(ValueError): builder.verify_package(self.package)

    def test_modified_missing_and_unreviewed_files_are_rejected(self):
        (self.package/'AI-Monitor.exe').write_text('changed')
        with self.assertRaises(ValueError): builder.verify_package(self.package)
        self.hashes(); (self.package/'extra.txt').write_text('unreviewed')
        with self.assertRaises(ValueError): builder.verify_package(self.package)
        (self.package/'extra.txt').unlink(); (self.package/'AI-Monitor-Console.exe').unlink(); self.hashes()
        with self.assertRaises(ValueError): builder.verify_package(self.package)

    def test_private_config_rejected_even_if_its_hash_is_added(self):
        path = self.package/'tools/aim_host.json'; path.parent.mkdir(exist_ok=True); path.write_text('{}'); self.hashes()
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
