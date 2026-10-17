"""Release exports include reviewed source, never runtime data or executables."""
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))

class TerminalExportTests(unittest.TestCase):
    def test_safe_source_is_copied(self):
        import build_terminal_release as build
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);source=root/'source';source.mkdir();target=root/'package';target.mkdir()
            (source/'LICENSE').write_bytes(b'original license bytes\r\n')
            with patch.object(build.subprocess,'check_output',return_value='LICENSE\n'):
                build.export_source(source,target)
            self.assertEqual((target/'LICENSE').read_bytes(),b'original license bytes\r\n')

    def test_private_generated_and_path_escape_exports_are_refused(self):
        import build_terminal_release as build
        for name in ('tools/aim_host.json','tools/activity/state.json','work/private.txt','runtime/unreviewed.dll','private.exe','escape/../../private.txt','.env','auth.json','link.lnk'):
            with self.subTest(name=name),tempfile.TemporaryDirectory() as directory:
                root=Path(directory);target=root/'package';target.mkdir()
                if name.startswith('runtime/'):
                    (root/name).parent.mkdir();(root/name).write_bytes(b'unreviewed runtime binary')
                with patch.object(build.subprocess,'check_output',return_value=name+'\n'):
                    with self.assertRaises(ValueError):build.export_source(root,target)

    def test_package_records_both_images_and_validates_each_operation(self):
        import hashlib,json,zipfile
        from types import SimpleNamespace
        import build_terminal_release as build
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);source=root/'source';source.mkdir();(source/'LICENSE').write_bytes(b'original')
            images=root/'images'
            for board in build.BOARDS:
                (images/board).mkdir(parents=True)
                for image in ('application.bin','factory.bin'):(images/board/image).write_bytes(b'fixture '+build.HOST_VERSION.encode())
            output=root/'out';output.mkdir();package=output/'nova-terminal';package.mkdir()
            with patch.object(build,'ROOT',source),patch.object(build.subprocess,'check_output',return_value='LICENSE\n'),patch.object(build,'firmware_file') as verify,patch('build_companion_packages.build'):
                build.build_package(output,package,build.HOST_VERSION,SimpleNamespace(firmware_dir=images))
            self.assertEqual(verify.call_count,4)
            manifest=json.loads((package/'firmware/manifest.json').read_text())
            self.assertEqual(set(manifest['boards']),set(build.BOARDS))
            for board,record in manifest['boards'].items():
                for name,data in record['files'].items():self.assertEqual(data['sha256'],hashlib.sha256((package/'firmware'/board/name).read_bytes()).hexdigest())
            with zipfile.ZipFile(output/'nova-terminal.zip') as archive:
                self.assertIsNone(archive.testzip());self.assertIn('nova-terminal/LICENSE',archive.namelist())
                self.assertFalse(any(name.endswith('.exe') for name in archive.namelist()))

if __name__=='__main__':unittest.main()
