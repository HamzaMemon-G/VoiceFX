"""Named session admission compatible with the existing VoiceFX audio host."""
import ctypes
import os

SESSION_MUTEX = 'Local\\VoiceFX.Stream'


class VoiceSessionLock:
    def __init__(self, name=SESSION_MUTEX):
        self.name = name
        self._handle = None
        self._kernel = None

    def __enter__(self):
        if os.name != 'nt':
            raise RuntimeError('Voice session admission requires Windows')
        if self._handle is not None:
            raise RuntimeError('Session lock already held')
        kernel = ctypes.WinDLL('kernel32', use_last_error=True)
        kernel.CreateMutexW.argtypes = [ctypes.c_void_p, ctypes.c_bool, ctypes.c_wchar_p]
        kernel.CreateMutexW.restype = ctypes.c_void_p
        kernel.CloseHandle.argtypes = [ctypes.c_void_p]
        ctypes.set_last_error(0)
        handle = kernel.CreateMutexW(None, False, self.name)
        error = ctypes.get_last_error()
        if not handle:
            raise RuntimeError('Cannot acquire audio session admission')
        if error == 183:
            kernel.CloseHandle(handle)
            raise RuntimeError('Another VoiceFX session is running. Stop it first.')
        self._kernel, self._handle = kernel, handle
        return self

    def __exit__(self, *exc):
        handle, self._handle = self._handle, None
        if handle is not None:
            self._kernel.CloseHandle(handle)
