"""Windows same-user named pipes. Bytes/JSON only; no TCP, pickle or command dispatch."""
import ctypes
from ctypes import wintypes as w
import json
import os
import re
import time

MAX_MESSAGE=4096


def strict_json(raw):
    if not isinstance(raw,bytes) or not 0<len(raw)<=MAX_MESSAGE:raise ValueError('Invalid IPC size')
    def pairs(items):
        output={}
        for key,value in items:
            if key in output:raise ValueError('Duplicate IPC field')
            output[key]=value
        return output
    return json.loads(raw,object_pairs_hook=pairs,parse_constant=lambda _:(_ for _ in ()).throw(ValueError('Invalid JSON number')))


def _api():
    if os.name!='nt':raise OSError('Permission pipes require Windows')
    kernel=ctypes.WinDLL('kernel32',use_last_error=True)
    advapi=ctypes.WinDLL('advapi32',use_last_error=True)
    return kernel,advapi


def current_sid():
    kernel,advapi=_api();token=w.HANDLE();needed=w.DWORD()
    kernel.GetCurrentProcess.restype=w.HANDLE
    advapi.OpenProcessToken.argtypes=[w.HANDLE,w.DWORD,ctypes.POINTER(w.HANDLE)]
    advapi.GetTokenInformation.argtypes=[w.HANDLE,ctypes.c_int,ctypes.c_void_p,w.DWORD,ctypes.POINTER(w.DWORD)]
    advapi.ConvertSidToStringSidW.argtypes=[ctypes.c_void_p,ctypes.POINTER(w.LPWSTR)]
    kernel.CloseHandle.argtypes=[w.HANDLE];kernel.LocalFree.argtypes=[ctypes.c_void_p]
    if not advapi.OpenProcessToken(kernel.GetCurrentProcess(),8,ctypes.byref(token)):raise ctypes.WinError(ctypes.get_last_error())
    try:
        advapi.GetTokenInformation(token,1,None,0,ctypes.byref(needed))
        if not 0<needed.value<=4096:raise ValueError('Invalid user token')
        buffer=ctypes.create_string_buffer(needed.value)
        if not advapi.GetTokenInformation(token,1,buffer,len(buffer),ctypes.byref(needed)):raise ctypes.WinError(ctypes.get_last_error())
        sid=ctypes.cast(buffer,ctypes.POINTER(ctypes.c_void_p))[0];text=w.LPWSTR()
        if not advapi.ConvertSidToStringSidW(sid,ctypes.byref(text)):raise ctypes.WinError(ctypes.get_last_error())
        try:return text.value
        finally:kernel.LocalFree(ctypes.cast(text,ctypes.c_void_p))
    finally:kernel.CloseHandle(token)


def _address(name):
    if not isinstance(name,str) or not re.fullmatch(r'ai-monitor-permission-[0-9a-f]{32}',name):raise ValueError('Invalid local pipe name')
    return '\\\\.\\pipe\\'+name


class Channel:
    def __init__(self,handle):
        from multiprocessing.connection import PipeConnection
        self.connection=PipeConnection(handle)
    def close(self):self.connection.close()
    def send(self,value):
        raw=json.dumps(value,ensure_ascii=True,separators=(',',':'),allow_nan=False).encode()
        if not 0<len(raw)<=MAX_MESSAGE:raise ValueError('IPC message too large')
        self.connection.send_bytes(raw)
    def receive(self,timeout):
        if type(timeout) not in (int,float) or not 0<timeout<=30:raise ValueError('Invalid IPC deadline')
        if not self.connection.poll(timeout):raise TimeoutError('Permission IPC expired')
        return strict_json(self.connection.recv_bytes(MAX_MESSAGE))
    def peer_pid(self,server):
        kernel,_=_api();pid=w.DWORD()
        method=kernel.GetNamedPipeClientProcessId if server else kernel.GetNamedPipeServerProcessId
        method.argtypes=[w.HANDLE,ctypes.POINTER(w.DWORD)]
        if not method(self.connection.fileno(),ctypes.byref(pid)) or not pid.value:raise OSError('IPC peer unavailable')
        return pid.value


class Listener:
    """One bounded connection; remote clients rejected by the kernel, owner SID only."""
    def __init__(self,name):
        kernel,advapi=_api();self.handle=None
        class Attributes(ctypes.Structure):
            _fields_=[('length',w.DWORD),('descriptor',ctypes.c_void_p),('inherit',w.BOOL)]
        descriptor=ctypes.c_void_p()
        advapi.ConvertStringSecurityDescriptorToSecurityDescriptorW.argtypes=[w.LPCWSTR,w.DWORD,ctypes.POINTER(ctypes.c_void_p),ctypes.c_void_p]
        kernel.CreateNamedPipeW.argtypes=[w.LPCWSTR,w.DWORD,w.DWORD,w.DWORD,w.DWORD,w.DWORD,w.DWORD,ctypes.POINTER(Attributes)]
        kernel.CreateNamedPipeW.restype=w.HANDLE;kernel.LocalFree.argtypes=[ctypes.c_void_p]
        self.sddl='D:P(A;;GA;;;'+current_sid()+')'
        if not advapi.ConvertStringSecurityDescriptorToSecurityDescriptorW(self.sddl,1,ctypes.byref(descriptor),None):raise ctypes.WinError(ctypes.get_last_error())
        try:
            attributes=Attributes(ctypes.sizeof(Attributes),descriptor,False)
            handle=kernel.CreateNamedPipeW(_address(name),3|0x40000000|0x80000,4|2|8,1,8192,8192,0,ctypes.byref(attributes))
            if handle==ctypes.c_void_p(-1).value:raise ctypes.WinError(ctypes.get_last_error())
            self.handle=handle
        finally:kernel.LocalFree(descriptor)
    def close(self):
        if self.handle is not None:
            import _winapi
            _winapi.CloseHandle(self.handle);self.handle=None
    def accept(self,timeout=5):
        if type(timeout) not in (int,float) or not 0<timeout<=30:raise ValueError('Invalid IPC deadline')
        import _winapi
        operation=_winapi.ConnectNamedPipe(self.handle,overlapped=True)
        if _winapi.WaitForSingleObject(operation.event,int(timeout*1000))!=0:
            operation.cancel();operation.GetOverlappedResult(True)
            raise TimeoutError('Permission IPC accept expired')
        _,error=operation.GetOverlappedResult(True)
        if error:raise OSError('Permission IPC connection failed')
        handle=self.handle;self.handle=None;return Channel(handle)


def connect(name,timeout=2):
    if type(timeout) not in (int,float) or not 0<timeout<=5:raise ValueError('Invalid IPC deadline')
    _api();import _winapi
    deadline=time.monotonic()+timeout
    while True:
        try:
            handle=_winapi.CreateFile(_address(name),_winapi.GENERIC_READ|_winapi.GENERIC_WRITE,0,0,
                _winapi.OPEN_EXISTING,_winapi.FILE_FLAG_OVERLAPPED,0)
            break
        except OSError as error:
            if error.winerror not in (2,231) or time.monotonic()>=deadline:raise
            time.sleep(.01)
    try:_winapi.SetNamedPipeHandleState(handle,_winapi.PIPE_READMODE_MESSAGE,None,None)
    except BaseException:_winapi.CloseHandle(handle);raise
    return Channel(handle)
