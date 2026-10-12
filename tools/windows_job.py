"""Contain explicitly launched workers before their first instruction executes."""
import ctypes
from ctypes import wintypes
import os
import time


class BasicLimits(ctypes.Structure):
    _fields_=[('process_time',ctypes.c_longlong),('job_time',ctypes.c_longlong),
        ('flags',wintypes.DWORD),('minimum',ctypes.c_size_t),('maximum',ctypes.c_size_t),
        ('active_limit',wintypes.DWORD),('affinity',ctypes.c_size_t),
        ('priority',wintypes.DWORD),('scheduling',wintypes.DWORD)]


class IoCounters(ctypes.Structure):
    _fields_=[(name,ctypes.c_ulonglong) for name in ('reads','writes','other','read_bytes','write_bytes','other_bytes')]


class ExtendedLimits(ctypes.Structure):
    _fields_=[('basic',BasicLimits),('io',IoCounters),('process_memory',ctypes.c_size_t),
        ('job_memory',ctypes.c_size_t),('peak_process',ctypes.c_size_t),('peak_job',ctypes.c_size_t)]


class Accounting(ctypes.Structure):
    _fields_=[(name,ctypes.c_longlong) for name in ('user','kernel','period_user','period_kernel')]+[
        (name,wintypes.DWORD) for name in ('faults','total','active','terminated')]


class ThreadEntry(ctypes.Structure):
    _fields_=[('size',wintypes.DWORD),('usage',wintypes.DWORD),('thread',wintypes.DWORD),
        ('owner',wintypes.DWORD),('priority',wintypes.LONG),('delta',wintypes.LONG),('flags',wintypes.DWORD)]


class WindowsJob:
    def __init__(self):
        if os.name!='nt': raise OSError('Windows process containment unavailable')
        self.handle=None
        api=self.api=ctypes.WinDLL('kernel32',use_last_error=True)
        signatures={
            'CreateJobObjectW':([ctypes.c_void_p,wintypes.LPCWSTR],wintypes.HANDLE),
            'SetInformationJobObject':([wintypes.HANDLE,ctypes.c_int,ctypes.c_void_p,wintypes.DWORD],wintypes.BOOL),
            'AssignProcessToJobObject':([wintypes.HANDLE,wintypes.HANDLE],wintypes.BOOL),
            'TerminateJobObject':([wintypes.HANDLE,wintypes.UINT],wintypes.BOOL),
            'QueryInformationJobObject':([wintypes.HANDLE,ctypes.c_int,ctypes.c_void_p,wintypes.DWORD,ctypes.c_void_p],wintypes.BOOL),
            'CloseHandle':([wintypes.HANDLE],wintypes.BOOL),
            'CreateToolhelp32Snapshot':([wintypes.DWORD,wintypes.DWORD],wintypes.HANDLE),
            'Thread32First':([wintypes.HANDLE,ctypes.POINTER(ThreadEntry)],wintypes.BOOL),
            'Thread32Next':([wintypes.HANDLE,ctypes.POINTER(ThreadEntry)],wintypes.BOOL),
            'OpenThread':([wintypes.DWORD,wintypes.BOOL,wintypes.DWORD],wintypes.HANDLE),
            'GetProcessIdOfThread':([wintypes.HANDLE],wintypes.DWORD),
            'ResumeThread':([wintypes.HANDLE],wintypes.DWORD),
        }
        for name,(arguments,result) in signatures.items():
            function=getattr(api,name); function.argtypes=arguments; function.restype=result
        self.handle=api.CreateJobObjectW(None,None)  # Unnamed and non-inheritable.
        if not self.handle: raise OSError('Cannot create worker containment')
        limits=ExtendedLimits(); limits.basic.flags=0x2000  # KILL_ON_JOB_CLOSE; no breakaway.
        if not api.SetInformationJobObject(self.handle,9,ctypes.byref(limits),ctypes.sizeof(limits)):
            self.release(); raise OSError('Cannot configure worker containment')

    def attach_and_resume(self,process):
        # CPython Popen retains the process handle, but closes its primary-thread handle.
        # CREATE_SUSPENDED prevents user code/children before assignment. Reopen only
        # that owned process's primary thread using the documented Toolhelp API.
        if not self.api.AssignProcessToJobObject(self.handle,int(process._handle)):
            raise OSError('Cannot assign worker containment')
        snapshot=self.api.CreateToolhelp32Snapshot(4,0)  # SNAPTHREAD
        if snapshot in (None,ctypes.c_void_p(-1).value): raise OSError('Cannot locate suspended worker thread')
        try:
            entry=ThreadEntry(); entry.size=ctypes.sizeof(entry)
            found=self.api.Thread32First(snapshot,ctypes.byref(entry))
            deadline=time.monotonic()+2
            while found and time.monotonic()<deadline:
                if entry.owner==process.pid:
                    thread=self.api.OpenThread(0x0802,False,entry.thread)  # QUERY_LIMITED + SUSPEND_RESUME
                    if not thread: raise OSError('Cannot open suspended worker thread')
                    try:
                        if self.api.GetProcessIdOfThread(thread)!=process.pid or process.poll() is not None:
                            raise OSError('Suspended worker identity changed')
                        if self.api.ResumeThread(thread)!=1: raise OSError('Cannot resume contained worker')
                        return
                    finally: self.api.CloseHandle(thread)
                entry.size=ctypes.sizeof(entry)
                found=self.api.Thread32Next(snapshot,ctypes.byref(entry))
            raise OSError('Suspended worker thread unavailable')
        finally: self.api.CloseHandle(snapshot)

    def active(self):
        info=Accounting()
        if not self.api.QueryInformationJobObject(self.handle,1,ctypes.byref(info),ctypes.sizeof(info),None):
            raise OSError('Cannot confirm worker containment cleanup')
        return info.active

    def stop(self):
        if self.handle is None: return
        if not self.api.TerminateJobObject(self.handle,1): raise OSError('Cannot terminate contained workers')
        deadline=time.monotonic()+3
        while self.active():
            if time.monotonic()>=deadline: raise RuntimeError('Contained workers still running; retry blocked')
            time.sleep(.01)
        self.release()

    def release(self):
        if self.handle is not None:
            if not self.api.CloseHandle(self.handle): raise OSError('Cannot close worker containment')
            self.handle=None

    def __del__(self):
        try: self.release()
        except (OSError,AttributeError): pass
