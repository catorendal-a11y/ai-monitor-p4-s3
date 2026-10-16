"""Export committed artwork, validate pixels and retain original notices in real packages."""
import hashlib
from pathlib import Path
import sys
import tempfile
import unittest
import zipfile
ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'scripts'),str(ROOT/'tools')]


class BuildCompanionPackagesTests(unittest.TestCase):
    def test_original_companions_export_as_reproducible_verified_version_two_archives(self):
        from build_companion_packages import build
        from companion_packages import parse_archive
        with tempfile.TemporaryDirectory() as directory:
            for robot in ('nova','orbit'):
                first=build(robot,Path(directory)/'one')
                second=build(robot,Path(directory)/'two')
                self.assertEqual(first.read_bytes(),second.read_bytes())
                pack=parse_archive(first.read_bytes())
                self.assertEqual(pack.manifest['version'],2)
                self.assertEqual(len(pack.manifest['frames']),6)
                self.assertEqual(len(pack.manifest['animations']),8)
                self.assertEqual(pack.manifest['codec'],'lz4')
                self.assertLess(len(pack.blob),2*1024*1024)
                with zipfile.ZipFile(first) as z:self.assertEqual(z.read('LICENSE'),(ROOT/'LICENSE').read_bytes())
