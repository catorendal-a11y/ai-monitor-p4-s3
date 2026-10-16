"""Bounded cross-process authority for opt-in history; no provider or USB access."""
from contextlib import contextmanager
import hashlib
import math
import os
from pathlib import Path
import threading
import time
from host_security import read_local_json
from private_files import write_json

LEASE_SECONDS=90
_local=threading.local()

@contextmanager
def lock(directory,timeout=1):
    folder=Path(directory).resolve();key=os.path.normcase(str(folder))
    depths=getattr(_local,'depths',None)
    if depths is None:depths=_local.depths={}
    if key in depths:
        depths[key]+=1
        try:yield
        finally:depths[key]-=1
        return
    if os.name=='nt':
        import ctypes
        from ctypes import wintypes as w
        from permission_ipc import current_sid
        kernel=ctypes.WinDLL('kernel32',use_last_error=True)
        kernel.CreateMutexW.argtypes=[ctypes.c_void_p,w.BOOL,w.LPCWSTR];kernel.CreateMutexW.restype=w.HANDLE
        kernel.WaitForSingleObject.argtypes=[w.HANDLE,w.DWORD]
        kernel.ReleaseMutex.argtypes=[w.HANDLE];kernel.CloseHandle.argtypes=[w.HANDLE]
        name='Global\\AI-Monitor-History-'+hashlib.sha256((current_sid()+':'+key).encode()).hexdigest()
        handle=kernel.CreateMutexW(None,False,name)
        if not handle:raise ctypes.WinError(ctypes.get_last_error())
        acquired=False
        try:
            status=kernel.WaitForSingleObject(handle,max(0,int(timeout*1000)))
            # An abandoned mutex is owned by us now: crashes cannot strand authority.
            if status not in (0,0x80):raise TimeoutError('History authority is busy')
            acquired=True;depths[key]=1
            try:yield
            finally:depths.pop(key,None)
        finally:
            if acquired:kernel.ReleaseMutex(handle)
            kernel.CloseHandle(handle)
    else:
        import fcntl
        path=folder.parent/('.'+folder.name+'-history-authority.lock')
        if path.is_symlink():raise ValueError('Invalid history authority path')
        with path.open('a+b') as stream:
            deadline=time.monotonic()+timeout
            while True:
                try:fcntl.flock(stream,fcntl.LOCK_EX|fcntl.LOCK_NB);break
                except BlockingIOError:
                    if time.monotonic()>=deadline:raise TimeoutError('History authority is busy')
                    time.sleep(min(.002,max(0,deadline-time.monotonic())))
            depths[key]=1
            try:yield
            finally:depths.pop(key,None);fcntl.flock(stream,fcntl.LOCK_UN)


def floor(directory):
    path=Path(directory)/'agent-history-revocation.json'
    if path.is_symlink():raise ValueError('Invalid history revocation path')
    if not path.exists():return 0
    value=read_local_json(path,128)
    if not isinstance(value,dict) or set(value)!={'epoch'} or type(value['epoch']) is not int or not 0<value['epoch']<(1<<63):
        raise ValueError('Invalid history revocation')
    return value['epoch']


def marker(directory):
    path=Path(directory)/'agent-history-consent.json'
    if path.is_symlink():raise ValueError('Invalid history consent path')
    return read_local_json(path,256) if path.exists() else None


def policy_allows(directory,policy_path=None):
    path=Path(policy_path) if policy_path is not None else Path(directory).parent/'aim_host.json'
    if policy_path is None and not path.exists():return True # Standalone synthetic/back-end stores.
    try:value=read_local_json(path,65536)
    except (OSError,ValueError,TypeError):return False
    return isinstance(value,dict) and value.get('usage_history') is True


def valid(value):
    return (isinstance(value,dict) and set(value)=={'enabled','epoch','expires_at'}
        and value['enabled'] is True and type(value['epoch']) is int and 0<value['epoch']<(1<<63)
        and type(value['expires_at']) in (int,float) and math.isfinite(value['expires_at'])
        and 0<value['expires_at']-time.time()<=LEASE_SECONDS)


def admitted(directory,value,policy_path=None):
    return valid(value) and value['epoch']>floor(directory) and policy_allows(directory,policy_path)


def mint_epoch(directory,request_epoch=None):
    folder=Path(directory);folder.mkdir(parents=True,exist_ok=True)
    with lock(folder):
        if request_epoch is not None and request_epoch<=floor(folder):
            raise ValueError('History enable request was revoked')
        current=marker(folder)
        previous=current.get('epoch',0) if isinstance(current,dict) and type(current.get('epoch')) is int else 0
        return max(time.time_ns(),floor(folder)+1,previous+1)


def publish_locked(directory,enabled,epoch,policy_path=None):
    folder=Path(directory);current=marker(folder)
    previous=current.get('epoch',0) if isinstance(current,dict) and type(current.get('epoch')) is int else 0
    if epoch<previous:return False
    if enabled and (epoch<=floor(folder) or not policy_allows(folder,policy_path)):return False
    write_json(folder/'agent-history-consent.json',dict(enabled=enabled,epoch=epoch,
        expires_at=time.time()+LEASE_SECONDS if enabled else 0))
    return True


def revoke_locked(directory):
    folder=Path(directory)
    if not folder.exists():return
    current=marker(folder)
    previous=current.get('epoch',0) if isinstance(current,dict) and type(current.get('epoch')) is int else 0
    epoch=max(time.time_ns(),floor(folder)+1,previous+1)
    # Floor first: a failed subsequent marker write still revokes old authority.
    write_json(folder/'agent-history-revocation.json',{'epoch':epoch})
    write_json(folder/'agent-history-consent.json',dict(enabled=False,epoch=epoch,expires_at=0))


@contextmanager
def policy_update(directory,enabled=False):
    if type(enabled) is not bool:raise ValueError('Invalid history preference')
    Path(directory).parent.mkdir(parents=True,exist_ok=True)
    with lock(directory):
        if not enabled:revoke_locked(directory)
        yield
