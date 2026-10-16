"""Atomic same-user settings and backups. Protect empty files before writing bytes."""
import ctypes
from ctypes import wintypes as w
import json
import os
from pathlib import Path
import tempfile
import time

def protect(path):
    if os.name!='nt':
        os.chmod(path,0o600);return
    from permission_ipc import current_sid
    api=ctypes.WinDLL('advapi32',use_last_error=True)
    kernel=ctypes.WinDLL('kernel32',use_last_error=True)
    descriptor=ctypes.c_void_p()
    api.ConvertStringSecurityDescriptorToSecurityDescriptorW.argtypes=[w.LPCWSTR,w.DWORD,ctypes.POINTER(ctypes.c_void_p),ctypes.c_void_p]
    api.SetFileSecurityW.argtypes=[w.LPCWSTR,w.DWORD,ctypes.c_void_p]
    kernel.LocalFree.argtypes=[ctypes.c_void_p]
    sddl='D:P(A;;FA;;;'+current_sid()+')(A;;FA;;;SY)'
    if not api.ConvertStringSecurityDescriptorToSecurityDescriptorW(sddl,1,ctypes.byref(descriptor),None):raise ctypes.WinError(ctypes.get_last_error())
    try:
        if not api.SetFileSecurityW(str(path),0x80000004,descriptor):raise ctypes.WinError(ctypes.get_last_error())
    finally:kernel.LocalFree(descriptor)

def write_bytes(path,data):
    path=Path(path)
    if path.is_symlink() or path.parent.is_symlink():raise ValueError('Invalid private settings path')
    path.parent.mkdir(parents=True,exist_ok=True)
    descriptor,temporary=tempfile.mkstemp(suffix='.tmp',dir=path.parent)
    try:
        with os.fdopen(descriptor,'wb') as stream:
            protect(temporary)
            stream.write(data);stream.flush();os.fsync(stream.fileno())
        for attempt in range(4):
            try:os.replace(temporary,path);break
            except PermissionError as error:
                if os.name!='nt' or getattr(error,'winerror',None) not in (5,32,33) or attempt==3:raise
                time.sleep(.025*(2**attempt))
    finally:
        if os.path.exists(temporary):os.unlink(temporary)

def write_json(path,value):
    write_bytes(path,(json.dumps(value,indent=2,allow_nan=False)+'\n').encode('utf-8'))

def backup(source,target):
    source=Path(source)
    if source.is_symlink():raise ValueError('Invalid private backup source')
    with source.open('rb') as stream:data=stream.read(65537)
    if len(data)>65536:raise ValueError('Private settings backup exceeds size limit')
    write_bytes(target,data)
