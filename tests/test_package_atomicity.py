"""Failed packaging must neither publish a truncated ZIP nor block a retry."""
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
import zipfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'scripts'))
import build_windows_release as build
from project_version import HOST_VERSION


class PackageAtomicityTests(unittest.TestCase):
    def test_reusing_executables_without_source_provenance_is_refused(self):
        with patch.object(build.sys, 'argv', ['build', '--firmware-dir', 'synthetic', '--executables-dir', 'old']), \
                patch.object(build, 'build_package') as package:
            with self.assertRaises(SystemExit) as error: build.main()
        self.assertEqual(error.exception.code, 2)
        package.assert_not_called()
    def test_failed_zip_write_preserves_existing_archive_and_removes_partial(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); package = root/'synthetic-package'; package.mkdir()
            (package/'public.txt').write_text('synthetic source', encoding='utf-8')
            archive = root/'package.zip'; before = b'existing reviewed archive'
            archive.write_bytes(before)
            with patch.object(build.zipfile.ZipFile, 'write', side_effect=OSError('synthetic disk failure')):
                with self.assertRaises(OSError): build.archive_package(package, archive)
            self.assertEqual(archive.read_bytes(), before)
            self.assertFalse(archive.with_name(archive.name+'.partial').exists())
            build.archive_package(package, archive)
            with zipfile.ZipFile(archive) as bundle:
                self.assertEqual(bundle.read('synthetic-package/public.txt'), b'synthetic source')

    def test_failed_package_build_removes_only_its_new_directory_and_allows_retry(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); (root/'src').mkdir()
            (root/'src/config.h').write_text('#define FW_VERSION "'+HOST_VERSION+'"\n', encoding='utf-8')
            output = root/'deliveries'; output.mkdir()
            preserved = output/'other-reviewed-file'; preserved.write_bytes(b'keep')
            arguments = ['build', '--firmware-dir', str(root/'fixtures'), '--output', str(output)]
            def fail(_output, package, *_args):
                (package/'half-written').write_bytes(b'partial')
                raise OSError('synthetic build failure')
            with patch.object(build, 'ROOT', root), patch.object(build.sys, 'argv', arguments), \
                    patch.object(build.sys, 'platform', 'win32'), \
                    patch.object(build.subprocess, 'check_output', return_value=str(root)), \
                    patch.object(build, 'build_package', side_effect=fail):
                with self.assertRaises(OSError): build.main()
            self.assertEqual(preserved.read_bytes(), b'keep')
            package = output/('ai-monitor-p4-'+HOST_VERSION+'-windows')
            self.assertFalse(package.exists())
            with patch.object(build, 'ROOT', root), patch.object(build.sys, 'argv', arguments), \
                    patch.object(build.sys, 'platform', 'win32'), \
                    patch.object(build.subprocess, 'check_output', return_value=str(root)), \
                    patch.object(build, 'build_package') as retry:
                build.main()
                retry.assert_called_once()
            self.assertTrue(package.is_dir())


if __name__ == '__main__': unittest.main()
