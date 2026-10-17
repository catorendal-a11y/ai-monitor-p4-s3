"""Integrity checks for the private, vendor-supplied NOVA Python runtime."""
import hashlib
import json
from pathlib import Path, PurePosixPath


def verify_runtime(root):
    folder=Path(root)/'runtime'
    if not folder.exists():return None
    try:
        manifest=folder/'manifest.json'
        if manifest.stat().st_size>4*1024*1024:raise ValueError('Oversized runtime manifest')
        data=json.loads(manifest.read_text(encoding='utf-8'))
        files=data['files']
        if data.get('schema')!=1 or not isinstance(files,dict) or 'python.exe' not in files:
            raise ValueError('Unsupported runtime manifest')
        for name,digest in files.items():
            relative=PurePosixPath(name)
            if relative.is_absolute() or '..' in relative.parts or '\\' in name or ':' in name:
                raise ValueError('Unsafe runtime path')
            path=folder/name
            if path.is_symlink() or not path.resolve().is_relative_to(folder.resolve()):
                raise ValueError('Linked runtime path')
            with path.open('rb') as stream:actual=hashlib.file_digest(stream,'sha256').hexdigest()
            if actual!=digest:raise ValueError('Runtime file changed: '+name)
        for path in folder.rglob('*'):
            if path.is_symlink():raise ValueError('Linked runtime path')
            if not path.is_file():continue
            relative=path.relative_to(folder)
            if relative.as_posix()=='manifest.json' or relative.as_posix() in files:continue
            if '__pycache__' in relative.parts and path.suffix=='.pyc':continue
            raise ValueError('Unexpected runtime file: '+relative.as_posix())
        return folder/'python.exe'
    except (OSError,KeyError,TypeError,json.JSONDecodeError) as error:
        raise ValueError('Bundled runtime is incomplete; extract the complete release again') from error
