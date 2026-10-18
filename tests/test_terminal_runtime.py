"""Bundled runtime integrity and safe upstream archive handling."""
import hashlib,json,os,subprocess
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
            licenses=root/'licenses';licenses.mkdir();(licenses/'pyserial-LICENSE.txt').write_bytes(b'pyserial license')
            hashed=root/'scripts';hashed.mkdir();(hashed/'requirements-runtime-win313-hashed.txt').write_text('fixture==1 --hash=sha256:'+'0'*64)
            with patch.object(build,'ROOT',root),patch.object(build,'HASHED_REQUIREMENTS',hashed/'requirements-runtime-win313-hashed.txt'),patch.object(build.sys,'platform','win32'),patch.object(build.urllib.request,'urlopen',return_value=io.BytesIO(b'archive')),patch.object(build,'extract_python',side_effect=extract),patch.object(build,'prepare_wheelhouse'),patch.object(build.subprocess,'run') as run:
                build.bundle_runtime(package)
            manifest=json.loads((package/'runtime/manifest.json').read_text())
            self.assertEqual(manifest['python_archive_sha256'],build.PYTHON_SHA256)
            self.assertIn('LICENSE.txt',manifest['files'])
            self.assertIn('licenses/pyserial-LICENSE.txt',manifest['files'])
            self.assertFalse((package/'runtime/Lib/site-packages/bin').exists())
            install=run.call_args_list[-2].args[0]
            self.assertIn('--only-binary=:all:',install);self.assertIn('3.13',install)
            self.assertIn('--require-hashes',install);self.assertIn('--no-index',install)
            self.assertIn(str(root/'scripts/requirements-runtime-win313-hashed.txt'),install)
            self.assertEqual(run.call_args_list[-1].args[0][1],'-B')
            with patch.object(build.sys,'platform','win32'),self.assertRaises(ValueError):build.bundle_runtime(package)
            with patch.object(build.sys,'platform','linux'),self.assertRaises(RuntimeError):build.bundle_runtime(package)

    @unittest.skipUnless(os.name=='nt','Windows PowerShell runtime gate')
    def test_powershell_gate_rejects_changed_extra_and_wrong_metadata(self):
        script=Path(__file__).resolve().parents[1]/'scripts/verify_terminal_runtime.ps1'
        def run_case(change):
            with tempfile.TemporaryDirectory() as directory:
                root=Path(directory);folder=root/'runtime';folder.mkdir()
                payload=b'fixture';(folder/'python.exe').write_bytes(payload)
                data={'schema':1,'python_version':'3.13.16','python_archive_sha256':'97dae5274cc54867065e8d5a3226e48c35017ed332a0fdb0e27d5b5821961297','files':{'python.exe':hashlib.sha256(payload).hexdigest()}}
                change(folder,data)
                (folder/'manifest.json').write_text(json.dumps(data),encoding='utf-8')
                return subprocess.run(['powershell','-NoProfile','-ExecutionPolicy','Bypass','-File',str(script),'-Root',str(root)],capture_output=True,text=True,timeout=20)
        self.assertEqual(run_case(lambda folder,data:None).returncode,0)
        self.assertNotEqual(run_case(lambda folder,data:(folder/'python.exe').write_bytes(b'changed')).returncode,0)
        self.assertNotEqual(run_case(lambda folder,data:(folder/'extra.txt').write_text('extra')).returncode,0)
        self.assertNotEqual(run_case(lambda folder,data:data.update(python_version='3.13.15')).returncode,0)

    def test_launcher_validates_bundled_runtime_before_executing_it(self):
        launcher=(Path(__file__).resolve().parents[1]/'AI-Monitor-Terminal.bat').read_text()
        self.assertIn('verify_terminal_runtime.ps1',launcher)
        self.assertLess(launcher.index('verify_terminal_runtime.ps1'),launcher.index('"%NOVA_PYTHON%" -B'))
        self.assertIn('-Root "%~dp0."',launcher)

    def test_package_check_allows_only_the_two_upstream_python_executables(self):
        from test_terminal_package import unexpected_executables
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);runtime=root/'runtime';runtime.mkdir()
            for name in ('python.exe','pythonw.exe'):(runtime/name).write_bytes(b'fixture')
            self.assertEqual(unexpected_executables(root),[])
            extra=runtime/'dependency.exe';extra.write_bytes(b'fixture')
            self.assertEqual(unexpected_executables(root),[extra.resolve()])

if __name__=='__main__':unittest.main()
