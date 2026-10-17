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
        for name in ('tools/aim_host.json','tools/activity/state.json','work/private.txt','private.exe','escape/../../private.txt','.env','auth.json','link.lnk'):
            with self.subTest(name=name),tempfile.TemporaryDirectory() as directory:
                root=Path(directory);target=root/'package';target.mkdir()
                with patch.object(build.subprocess,'check_output',return_value=name+'\n'):
                    with self.assertRaises(ValueError):build.export_source(root,target)

if __name__=='__main__':unittest.main()
