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

    def test_missing_manifest_unsafe_name_and_changed_schema(self):
        from terminal_runtime import verify_runtime
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);folder=root/'runtime';folder.mkdir()
            with self.assertRaises(ValueError):verify_runtime(root)
            for data in ({'schema':2,'files':{}},{'schema':1,'files':{'python.exe':'0'*64,'../outside':'0'*64}}):
                (folder/'manifest.json').write_text(json.dumps(data))
                with self.assertRaises(ValueError):verify_runtime(root)

    def test_verified_archive_is_extracted_and_links_are_rejected(self):
        from bundle_terminal_runtime import extract_python
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);archive=root/'python.zip'
            with zipfile.ZipFile(archive,'w') as bundle:bundle.writestr('LICENSE.txt',b'original')
            extract_python(archive,root/'good',hashlib.sha256(archive.read_bytes()).hexdigest())
            self.assertEqual((root/'good/LICENSE.txt').read_bytes(),b'original')
            item=zipfile.ZipInfo('link');item.external_attr=0o120777<<16
            with zipfile.ZipFile(archive,'w') as bundle:bundle.writestr(item,b'elsewhere')
            with self.assertRaises(ValueError):extract_python(archive,root/'bad',hashlib.sha256(archive.read_bytes()).hexdigest())

    def test_bundler_resolves_pinned_windows_wheels_and_records_original_licenses(self):
        import io
        from unittest.mock import patch
        import bundle_terminal_runtime as build
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);package=root/'package';package.mkdir()
            def extract(archive,folder):
                folder.mkdir();(folder/'python.exe').write_bytes(b'interpreter');(folder/'LICENSE.txt').write_bytes(b'original license')
                wrappers=folder/'Lib/site-packages/bin';wrappers.mkdir(parents=True);(wrappers/'unused.exe').write_bytes(b'generated wrapper')
            with patch.object(build,'ROOT',root),patch.object(build.sys,'platform','win32'),patch.object(build.urllib.request,'urlopen',return_value=io.BytesIO(b'archive')),patch.object(build,'extract_python',side_effect=extract),patch.object(build.subprocess,'run') as run:
                build.bundle_runtime(package)
            manifest=json.loads((package/'runtime/manifest.json').read_text())
            self.assertEqual(manifest['python_archive_sha256'],build.PYTHON_SHA256)
            self.assertIn('LICENSE.txt',manifest['files'])
            self.assertFalse((package/'runtime/Lib/site-packages/bin').exists())
            install=run.call_args_list[1].args[0]
            self.assertIn('--only-binary=:all:',install);self.assertIn('3.13',install)
            self.assertIn(str(root/'scripts/requirements-runtime-win313.txt'),install)
            self.assertEqual(run.call_args_list[-1].args[0][1],'-B')
            with patch.object(build.sys,'platform','win32'),self.assertRaises(ValueError):build.bundle_runtime(package)
            with patch.object(build.sys,'platform','linux'),self.assertRaises(RuntimeError):build.bundle_runtime(package)

if __name__=='__main__':unittest.main()
