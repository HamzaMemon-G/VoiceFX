"""Read-only guard for automated heavy tests; never close or alter a game."""
import ctypes
from ctypes import wintypes
import json
import os
from threading import Event, Lock, Thread


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


class GameLoadWatch:
    """Abort only the supplied owned workload if a game starts after preflight."""
    def __init__(self,abort,interval=1.):
        self._abort=abort
        self._interval=interval
        self._stop=Event()
        self._lock=Lock()
        self._games=[]
        self._error=None
        self._thread=Thread(target=self._run,daemon=True,name='voicefx-resource-watch')
        self._thread.start()

    def _run(self):
        while not self._stop.is_set():
            try:
                games=active_games()
            except Exception as exc:
                with self._lock:
                    self._error=type(exc).__name__
                self._abort('CPU check stopped: resource availability could not be verified')
                return
            if games:
                with self._lock:
                    self._games=games
                self._abort('CPU check stopped because a game started')
                return
            self._stop.wait(self._interval)

    def status(self):
        with self._lock:
            return dict(blocked=bool(self._games or self._error),games=list(self._games),error=self._error)

    def close(self):
        self._stop.set()
        self._thread.join(timeout=2)
        if self._thread.is_alive():
            raise RuntimeError('Resource watcher did not stop')


if __name__=='__main__':
    games=active_games()
    print(json.dumps(dict(heavy_tests_allowed=not games,games=games)))
