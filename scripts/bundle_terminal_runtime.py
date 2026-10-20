"""Vendor official CPython and pinned Python packages for offline Windows startup.

NOVA remains source code. No project executable or graphical runtime is compiled.
"""
import hashlib
import json
import os
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
ESPTOOL_SOURCE_SHA256='fd756598db0a26c9975fa18511b08687c54bf2ce7322ede80cf1f5117dad1f50'
ESPTOOL_WHEEL_SHA256='a432dc49de9a5bc38306344bb365ae58d59618e6d4e08b2c837e05d341faad09'
# esptool ships only an sdist. Its wheel bytes depend on the setuptools version, so the
# build backend is hash-pinned too instead of letting build isolation fetch the latest one.
BUILD_SETUPTOOLS='setuptools==84.0.0'
BUILD_SETUPTOOLS_SHA256='51a52592b3b99e102b609654876bd65f19f999935166d1352678931132b0c670'
HASHED_REQUIREMENTS=ROOT/'scripts/requirements-runtime-win313-hashed.txt'


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


def _sha256(path):
    with Path(path).open('rb') as stream:return hashlib.file_digest(stream,'sha256').hexdigest()


def build_python(scratch):
    folder=scratch/('esptool-build-'+BUILD_SETUPTOOLS.replace('==','-'))
    return folder/('Scripts/python.exe' if os.name=='nt' else 'bin/python')


def prepare_build_environment(scratch):
    """A dedicated environment holding only the hash-checked wheel build backend."""
    python=build_python(scratch)
    if not python.exists():
        subprocess.run([sys.executable,'-m','venv',str(python.parents[1])],check=True)
    requirements=scratch/'esptool-build-requirements.txt'
    requirements.write_text(BUILD_SETUPTOOLS+' --hash=sha256:'+BUILD_SETUPTOOLS_SHA256+'\n',encoding='ascii')
    subprocess.run([str(python),'-m','pip','install','--disable-pip-version-check','--no-deps',
        '--require-hashes','-r',str(requirements)],check=True)
    return python


def prepare_wheelhouse(scratch,wheels):
    """Build one reproducible pure-Python wheel, then hash-check every Windows wheel."""
    wheels.mkdir(parents=True,exist_ok=True)
    sources=scratch/'sources';sources.mkdir(exist_ok=True)
    source=sources/'esptool-5.4.0.tar.gz'
    if not source.exists():
        subprocess.run([sys.executable,'-m','pip','download','--no-cache-dir','--no-deps',
            '--no-binary=:all:','--dest',str(sources),'esptool==5.4.0'],check=True)
    if _sha256(source)!=ESPTOOL_SOURCE_SHA256:raise ValueError('esptool source archive checksum mismatch')
    wheel=wheels/'esptool-5.4.0-py3-none-any.whl'
    if not wheel.exists():
        environment=dict(os.environ,SOURCE_DATE_EPOCH='1767225600')
        python=prepare_build_environment(scratch)
        subprocess.run([str(python),'-m','pip','wheel','--no-cache-dir','--no-deps','--no-build-isolation',
            '--wheel-dir',str(wheels),str(source)],check=True,env=environment)
    if _sha256(wheel)!=ESPTOOL_WHEEL_SHA256:raise ValueError('esptool wheel checksum mismatch')
    subprocess.run([sys.executable,'-m','pip','download','--dest',str(wheels),
        '--require-hashes','--only-binary=:all:','--platform','win_amd64','--python-version','3.13',
        '--implementation','cp','--abi','cp313','--find-links',str(wheels),'-r',str(HASHED_REQUIREMENTS)],check=True)


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
    wheels=scratch/'wheelhouse-cp313-v1'
    prepare_wheelhouse(scratch,wheels)
    subprocess.run([sys.executable,'-m','pip','install','--target',str(folder/'Lib/site-packages'),
        '--no-compile','--require-hashes','--no-index','--only-binary=:all:','--platform','win_amd64',
        '--python-version','3.13','--implementation','cp','--abi','cp313','--find-links',str(wheels),
        '-r',str(HASHED_REQUIREMENTS)],check=True)
    # Generated console shims point to the builder interpreter and are not used.
    # NOVA invokes Python modules directly; retain only the upstream interpreter.
    wrappers=folder/'Lib/site-packages/bin'
    if wrappers.exists():
        if wrappers.is_symlink() or not wrappers.resolve().is_relative_to(folder.resolve()):
            raise ValueError('Unsafe generated-wrapper directory')
        shutil.rmtree(wrappers)
    licenses=folder/'licenses';licenses.mkdir()
    shutil.copyfile(ROOT/'licenses/pyserial-LICENSE.txt',licenses/'pyserial-LICENSE.txt')
    (folder/'python313._pth').write_text('python313.zip\n.\nLib/site-packages\n../tools\nimport site\n',encoding='ascii')
    files={path.relative_to(folder).as_posix():hashlib.sha256(path.read_bytes()).hexdigest()
           for path in sorted(folder.rglob('*')) if path.is_file()}
    data=dict(schema=1,python_version=PYTHON_VERSION,architecture='win-amd64',
              python_archive_url=PYTHON_URL,python_archive_sha256=PYTHON_SHA256,files=files)
    (folder/'manifest.json').write_text(json.dumps(data,indent=2)+'\n',encoding='utf-8')
    subprocess.run([str(folder/'python.exe'),'-B','-c',
        'import serial,psutil,cryptography,lz4,textual,esptool; import sqlite3,ssl,ctypes; print("Bundled runtime imports passed")'],
        cwd=package,check=True,timeout=30)
