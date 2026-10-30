"""Read-only guard for automated heavy tests; never close or alter a game."""
import ctypes
from ctypes import wintypes
import json
import os


def is_game(name):
    name=name.casefold()
    return name.startswith(('fortniteclient','fivem','hogwartslegacy','gta5','rdr2','cyberpunk2077'))


class ProcessEntry(ctypes.Structure):
    _fields_=[('size',wintypes.DWORD),('usage',wintypes.DWORD),('pid',wintypes.DWORD),
        ('heap',ctypes.c_size_t),('module',wintypes.DWORD),('threads',wintypes.DWORD),
        ('parent_pid',wintypes.DWORD),('priority',wintypes.LONG),('flags',wintypes.DWORD),
        ('name',wintypes.WCHAR*260)]


def active_games():
    if os.name!='nt':
        raise RuntimeError('This resource guard requires Windows')
    kernel=ctypes.WinDLL('kernel32',use_last_error=True)
    kernel.CreateToolhelp32Snapshot.argtypes=[wintypes.DWORD,wintypes.DWORD]
    kernel.CreateToolhelp32Snapshot.restype=wintypes.HANDLE
    for name in ('Process32FirstW','Process32NextW'):
        getattr(kernel,name).argtypes=[wintypes.HANDLE,ctypes.POINTER(ProcessEntry)]
        getattr(kernel,name).restype=wintypes.BOOL
    kernel.CloseHandle.argtypes=[wintypes.HANDLE]
    snapshot=kernel.CreateToolhelp32Snapshot(2,0)
    if snapshot==ctypes.c_void_p(-1).value:
        raise ctypes.WinError(ctypes.get_last_error())
    found=[]
    try:
        entry=ProcessEntry()
        entry.size=ctypes.sizeof(entry)
        more=kernel.Process32FirstW(snapshot,ctypes.byref(entry))
        while more:
            if is_game(entry.name):
                found.append(dict(name=entry.name,pid=int(entry.pid)))
            more=kernel.Process32NextW(snapshot,ctypes.byref(entry))
    finally:
        kernel.CloseHandle(snapshot)
    return found


if __name__=='__main__':
    games=active_games()
    print(json.dumps(dict(heavy_tests_allowed=not games,games=games)))
