"""Atomic same-user settings and backups. Protect empty files before writing bytes."""
import ctypes
from ctypes import wintypes as w
import json
import os
from pathlib import Path
import tempfile
import time
import secrets

def temporary_file(directory):
    if os.name!='nt':return tempfile.mkstemp(suffix='.tmp',dir=directory)
    # Supply the DACL to CreateFile itself; even an empty inherited-ACL window
    # could let another user retain a readable handle before protection changes.
    import msvcrt
    from permission_ipc import current_sid
    api=ctypes.WinDLL('advapi32',use_last_error=True)
    kernel=ctypes.WinDLL('kernel32',use_last_error=True)
    descriptor=ctypes.c_void_p()
    api.ConvertStringSecurityDescriptorToSecurityDescriptorW.argtypes=[w.LPCWSTR,w.DWORD,ctypes.POINTER(ctypes.c_void_p),ctypes.c_void_p]
    kernel.LocalFree.argtypes=[ctypes.c_void_p]
    class Attributes(ctypes.Structure):
        _fields_=[('length',w.DWORD),('descriptor',ctypes.c_void_p),('inherit',w.BOOL)]
    kernel.CreateFileW.argtypes=[w.LPCWSTR,w.DWORD,w.DWORD,ctypes.POINTER(Attributes),w.DWORD,w.DWORD,w.HANDLE]
    kernel.CreateFileW.restype=w.HANDLE
    kernel.CloseHandle.argtypes=[w.HANDLE]
    sddl='D:P(A;;FA;;;'+current_sid()+')(A;;FA;;;SY)'
    if not api.ConvertStringSecurityDescriptorToSecurityDescriptorW(sddl,1,ctypes.byref(descriptor),None):raise ctypes.WinError(ctypes.get_last_error())
    try:
        attributes=Attributes(ctypes.sizeof(Attributes),descriptor,False)
        path=str(Path(directory)/('.private-'+secrets.token_hex(16)+'.tmp'))
        handle=kernel.CreateFileW(path,0x40000000,1,ctypes.byref(attributes),1,0x80,None)
        if handle==ctypes.c_void_p(-1).value:raise ctypes.WinError(ctypes.get_last_error())
        try:return msvcrt.open_osfhandle(handle,os.O_WRONLY|os.O_BINARY),path
        except BaseException:
            kernel.CloseHandle(handle);os.unlink(path);raise
    finally:kernel.LocalFree(descriptor)

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
    descriptor,temporary=temporary_file(path.parent)
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
