"""Own only the newly created worker tree, including Windows venv launchers."""
import ctypes
from ctypes import wintypes
from threading import Lock


class BasicLimits(ctypes.Structure):
    _fields_=[('process_time',ctypes.c_longlong),('job_time',ctypes.c_longlong),
        ('flags',wintypes.DWORD),('min_working_set',ctypes.c_size_t),
        ('max_working_set',ctypes.c_size_t),('active_processes',wintypes.DWORD),
        ('affinity',ctypes.c_size_t),('priority',wintypes.DWORD),('scheduling',wintypes.DWORD)]


class IoCounters(ctypes.Structure):
    _fields_=[(name,ctypes.c_ulonglong) for name in
        ('read_ops','write_ops','other_ops','read_bytes','write_bytes','other_bytes')]


class ExtendedLimits(ctypes.Structure):
    _fields_=[('basic',BasicLimits),('io',IoCounters),
        ('process_memory',ctypes.c_size_t),('job_memory',ctypes.c_size_t),
        ('peak_process_memory',ctypes.c_size_t),('peak_job_memory',ctypes.c_size_t)]


class ThreadEntry(ctypes.Structure):
    _fields_=[('size',wintypes.DWORD),('usage',wintypes.DWORD),
        ('thread_id',wintypes.DWORD),('process_id',wintypes.DWORD),
        ('base_priority',wintypes.LONG),('delta_priority',wintypes.LONG),('flags',wintypes.DWORD)]


class WindowsWorkerJob:
    """Assign a suspended, owned worker before it can create any descendants."""
    suspended_creation_flag=0x4

    def __init__(self):
        self._lock=Lock()
        self.kernel=ctypes.WinDLL('kernel32',use_last_error=True)
        api=self.kernel
        api.CreateJobObjectW.argtypes=[ctypes.c_void_p,wintypes.LPCWSTR]
        api.CreateJobObjectW.restype=wintypes.HANDLE
        api.SetInformationJobObject.argtypes=[wintypes.HANDLE,ctypes.c_int,ctypes.c_void_p,wintypes.DWORD]
        api.SetInformationJobObject.restype=wintypes.BOOL
        api.AssignProcessToJobObject.argtypes=[wintypes.HANDLE,wintypes.HANDLE]
        api.AssignProcessToJobObject.restype=wintypes.BOOL
        api.CloseHandle.argtypes=[wintypes.HANDLE]
        api.CloseHandle.restype=wintypes.BOOL
        api.CreateToolhelp32Snapshot.argtypes=[wintypes.DWORD,wintypes.DWORD]
        api.CreateToolhelp32Snapshot.restype=wintypes.HANDLE
        for name in ('Thread32First','Thread32Next'):
            getattr(api,name).argtypes=[wintypes.HANDLE,ctypes.POINTER(ThreadEntry)]
            getattr(api,name).restype=wintypes.BOOL
        api.OpenThread.argtypes=[wintypes.DWORD,wintypes.BOOL,wintypes.DWORD]
        api.OpenThread.restype=wintypes.HANDLE
        api.ResumeThread.argtypes=[wintypes.HANDLE]
        api.ResumeThread.restype=wintypes.DWORD
        self._handle=api.CreateJobObjectW(None,None)
        if not self._handle:
            raise ctypes.WinError(ctypes.get_last_error())
        limits=ExtendedLimits()
        limits.basic.flags=0x2000  # JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
        if not api.SetInformationJobObject(self._handle,9,ctypes.byref(limits),ctypes.sizeof(limits)):
            code=ctypes.get_last_error()
            self.close()
            raise ctypes.WinError(code)

    def assign_and_resume(self,process):
        with self._lock:
            if not self._handle:
                raise RuntimeError('Worker job already closed')
            if not self.kernel.AssignProcessToJobObject(self._handle,int(process._handle)):
                raise ctypes.WinError(ctypes.get_last_error())
            snapshot=self.kernel.CreateToolhelp32Snapshot(0x4,0)
            if snapshot==ctypes.c_void_p(-1).value:
                raise ctypes.WinError(ctypes.get_last_error())
            try:
                entry=ThreadEntry()
                entry.size=ctypes.sizeof(entry)
                found=self.kernel.Thread32First(snapshot,ctypes.byref(entry))
                while found:
                    if entry.process_id==process.pid:
                        thread=self.kernel.OpenThread(0x2,False,entry.thread_id)
                        if not thread:
                            raise ctypes.WinError(ctypes.get_last_error())
                        try:
                            if self.kernel.ResumeThread(thread)!=1:
                                raise RuntimeError('Owned worker thread was not suspended once')
                        finally:
                            self.kernel.CloseHandle(thread)
                        return
                    found=self.kernel.Thread32Next(snapshot,ctypes.byref(entry))
                raise RuntimeError('Suspended worker primary thread not found')
            finally:
                self.kernel.CloseHandle(snapshot)

    def close(self):
        with self._lock:
            if self._handle:
                handle,self._handle=self._handle,None
                if not self.kernel.CloseHandle(handle):
                    raise ctypes.WinError(ctypes.get_last_error())
