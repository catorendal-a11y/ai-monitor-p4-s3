"""Bundled runtime integrity and safe upstream archive handling."""
import hashlib,json
from pathlib import Path
import sys,tempfile,unittest,zipfile
sys.path[:0]=[str(Path(__file__).resolve().parents[1]/'tools'),str(Path(__file__).resolve().parents[1]/'scripts')]

class BundledRuntimeTests(unittest.TestCase):
    def fixture(self,root):
        folder=root/'runtime';folder.mkdir();(folder/'python.exe').write_bytes(b'fixture interpreter')
        (folder/'manifest.json').write_text(json.dumps({'schema':1,'files':{'python.exe':hashlib.sha256(b'fixture interpreter').hexdigest()}}))
        return folder

    def test_source_install_has_no_bundled_runtime(self):
        from terminal_runtime import verify_runtime
        with tempfile.TemporaryDirectory() as directory:self.assertIsNone(verify_runtime(Path(directory)))

    def test_modification_and_extra_executable_are_rejected(self):
        from terminal_runtime import verify_runtime
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);folder=self.fixture(root)
            self.assertEqual(verify_runtime(root),folder/'python.exe')
            (folder/'python.exe').write_bytes(b'changed')
            with self.assertRaises(ValueError):verify_runtime(root)
            (folder/'python.exe').write_bytes(b'fixture interpreter');(folder/'extra.exe').write_bytes(b'extra')
            with self.assertRaises(ValueError):verify_runtime(root)

    def test_python_cache_is_allowed_but_cache_executables_are_not(self):
        from terminal_runtime import verify_runtime
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);folder=self.fixture(root);cache=folder/'__pycache__';cache.mkdir();(cache/'cached.pyc').write_bytes(b'cache')
            self.assertEqual(verify_runtime(root),folder/'python.exe')
            (cache/'bad.exe').write_bytes(b'not cache')
            with self.assertRaises(ValueError):verify_runtime(root)

    def test_archive_hash_and_path_escape_are_checked_before_extract(self):
        from bundle_terminal_runtime import extract_python
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);archive=root/'python.zip';target=root/'python'
            with zipfile.ZipFile(archive,'w') as bundle:bundle.writestr('../escape.txt',b'bad')
            with self.assertRaises(ValueError):extract_python(archive,target,'0'*64)
            digest=hashlib.sha256(archive.read_bytes()).hexdigest()
            with self.assertRaises(ValueError):extract_python(archive,target,digest)
            self.assertFalse((root/'escape.txt').exists())

if __name__=='__main__':unittest.main()
