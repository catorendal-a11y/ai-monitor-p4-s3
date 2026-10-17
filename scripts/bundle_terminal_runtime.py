"""Vendor official CPython and pinned Python packages for offline Windows startup.

NOVA remains source code. No project executable or graphical runtime is compiled.
"""
import hashlib
import json
import shutil
from pathlib import Path, PurePosixPath
import subprocess
import sys
import urllib.request
import zipfile

ROOT=Path(__file__).resolve().parents[1]
PYTHON_VERSION='3.13.16'
PYTHON_URL='https://www.python.org/ftp/python/3.13.16/python-3.13.16-embed-amd64.zip'
PYTHON_SHA256='97dae5274cc54867065e8d5a3226e48c35017ed332a0fdb0e27d5b5821961297'


def extract_python(archive,target,digest=PYTHON_SHA256):
    if hashlib.sha256(archive.read_bytes()).hexdigest()!=digest:
        raise ValueError('Official Python archive checksum mismatch')
    with zipfile.ZipFile(archive) as bundle:
        for info in bundle.infolist():
            name=PurePosixPath(info.filename)
            if name.is_absolute() or '..' in name.parts or '\\' in info.filename or ':' in info.filename:
                raise ValueError('Unsafe Python archive path')
            if (info.external_attr>>16)&0o170000==0o120000:raise ValueError('Linked Python archive member')
        bundle.extractall(target)


def bundle_runtime(package):
    if sys.platform!='win32':raise RuntimeError('Build the Windows runtime on Windows')
    folder=Path(package)/'runtime'
    if folder.exists():raise ValueError('Runtime destination already exists')
    scratch=ROOT/'work/runtime-builder';scratch.mkdir(parents=True,exist_ok=True)
    archive=scratch/'python-3.13.16-embed-amd64.zip'
    if not archive.exists():
        with urllib.request.urlopen(PYTHON_URL,timeout=60) as response:
            data=response.read(20_000_001)
        if len(data)>20_000_000:raise ValueError('Oversized Python archive')
        archive.write_bytes(data)
    extract_python(archive,folder)
    wheels=scratch/'wheels';wheels.mkdir(exist_ok=True)
    # esptool is published as source. Build its pure-Python wheel on the builder,
    # then resolve Windows CPython 3.13 binary wheels for all runtime dependencies.
    subprocess.run([sys.executable,'-m','pip','wheel','--no-deps','--wheel-dir',str(wheels),'esptool==5.4.0'],check=True)
    subprocess.run([sys.executable,'-m','pip','install','--target',str(folder/'Lib/site-packages'),
        '--no-compile','--only-binary=:all:','--platform','win_amd64','--python-version','3.13',
        '--implementation','cp','--abi','cp313','--find-links',str(wheels),
        '-c',str(ROOT/'scripts/requirements-runtime-win313.txt'),
        '-r',str(ROOT/'tools/requirements.txt')],check=True)
    # Generated console shims point to the builder interpreter and are not used.
    # NOVA invokes Python modules directly; retain only the upstream interpreter.
    wrappers=folder/'Lib/site-packages/bin'
    if wrappers.exists():
        if wrappers.is_symlink() or not wrappers.resolve().is_relative_to(folder.resolve()):
            raise ValueError('Unsafe generated-wrapper directory')
        shutil.rmtree(wrappers)
    (folder/'python313._pth').write_text('python313.zip\n.\nLib/site-packages\n../tools\nimport site\n',encoding='ascii')
    files={path.relative_to(folder).as_posix():hashlib.sha256(path.read_bytes()).hexdigest()
           for path in sorted(folder.rglob('*')) if path.is_file()}
    data=dict(schema=1,python_version=PYTHON_VERSION,architecture='win-amd64',
              python_archive_url=PYTHON_URL,python_archive_sha256=PYTHON_SHA256,files=files)
    (folder/'manifest.json').write_text(json.dumps(data,indent=2)+'\n',encoding='utf-8')
    subprocess.run([str(folder/'python.exe'),'-B','-c',
        'import serial,psutil,cryptography,lz4,textual,esptool; import sqlite3,ssl,ctypes; print("Bundled runtime imports passed")'],
        cwd=package,check=True,timeout=30)
