"""Opt-in host seam. Opens no devices and changes no saved preferences."""

from threading import Lock

import numpy as np

from rvc_capture_bridge import RvcCaptureBridge
from monitor import Monitor


class RvcHostSession:
    """Own one worker and packetizer without a second audio queue.

    Start outside the audio callback. Close before tearing down host devices.
    A stopped session cannot be restarted; construct a new explicit session.
    """

    def __init__(self):
        self._lock = Lock()
        self._started = False
        self._closed = False
        self._stream = None
        self._bridge = None
        self.monitor = Monitor()

    def start(self, stream_factory):
        with self._lock:
            if self._started or self._closed:
                raise RuntimeError("Session already started or stopped")
            self._started = True
        stream = None
        try:
            stream = stream_factory()
            bridge = RvcCaptureBridge(stream)
        except Exception:
            self.close()
            if stream is not None:
                stream.close()
            raise
        with self._lock:
            cancelled = self._closed
            if not cancelled:
                self._stream = stream
                self._bridge = bridge
        if cancelled:
            stream.close()

    def process(self, capture):
        # No blocking lifecycle lock, model execution or pipe I/O in callback.
        bridge = self._bridge
        if self._closed or bridge is None:
            return np.zeros(len(capture), dtype=np.float32)
        output = bridge.process(capture)
        # Stop may arrive while the bounded packetizer is executing.
        if self._closed:
            return np.zeros(len(capture), dtype=np.float32)
        self.monitor.submit(output)
        return output

    def status(self):
        if self._closed:
            return {"state": "stopped", "ready": False}
        stream = self._stream
        if stream is None:
            return {"state": "initializing" if self._started else "idle", "ready": False}
        return stream.status()

    def close(self):
        with self._lock:
            self._closed = True
            stream, self._stream = self._stream, None
            self._bridge = None
        if stream is not None:
            stream.close()

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()
