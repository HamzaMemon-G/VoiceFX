"""Optional worker-local execution-speed hint, matching the existing audio host.

No global power plan, registry, security setting or other process is changed.
The request ends with this process. It does not establish CPU headroom.
"""
import ctypes
from ctypes import wintypes
import os


class PowerState(ctypes.Structure):
    _fields_=[('version',wintypes.ULONG),('control',wintypes.ULONG),('state',wintypes.ULONG)]


def execution_speed_state(disable_throttling=False):
    if type(disable_throttling) is not bool:
        raise ValueError('Execution-speed request must be explicitly boolean')
    if os.name!='nt':
        raise RuntimeError('Worker-local execution-speed hint requires Windows')
    kernel=ctypes.WinDLL('kernel32',use_last_error=True)
    kernel.GetCurrentProcess.restype=wintypes.HANDLE
    kernel.GetProcessInformation.argtypes=[wintypes.HANDLE,ctypes.c_int,ctypes.c_void_p,wintypes.DWORD]
    kernel.GetProcessInformation.restype=wintypes.BOOL
    kernel.SetProcessInformation.argtypes=[wintypes.HANDLE,ctypes.c_int,ctypes.c_void_p,wintypes.DWORD]
    kernel.SetProcessInformation.restype=wintypes.BOOL
    handle=kernel.GetCurrentProcess()
    before=PowerState(1,0,0)
    if not kernel.GetProcessInformation(handle,4,ctypes.byref(before),ctypes.sizeof(before)):
        raise ctypes.WinError(ctypes.get_last_error())
    if disable_throttling:
        requested=PowerState(1,int(before.control)|1,int(before.state)&~1)
        if not kernel.SetProcessInformation(handle,4,ctypes.byref(requested),ctypes.sizeof(requested)):
            raise ctypes.WinError(ctypes.get_last_error())
    after=PowerState(1,0,0)
    if not kernel.GetProcessInformation(handle,4,ctypes.byref(after),ctypes.sizeof(after)):
        raise ctypes.WinError(ctypes.get_last_error())
    applied=bool(after.control&1 and not after.state&1)
    if disable_throttling and not applied:
        raise RuntimeError('Worker-local execution-speed request was not acknowledged')
    return dict(requested=disable_throttling,applied=applied,pid=os.getpid(),
        before_control_mask=int(before.control),before_state_mask=int(before.state),
        control_mask=int(after.control),state_mask=int(after.state),
        scope='This worker process only; not a measured frequency or CPU timing guarantee')
