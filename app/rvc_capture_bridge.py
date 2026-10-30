"""Offline-tested mono callback packetizer; not enabled by the audio app."""

import numpy as np


class RvcCaptureBridge:
    """Adapt arbitrary callback boundaries to fixed model packets.

    Model execution and pipe I/O remain in the process transport. Startup capture
    is discarded until that worker is ready. This class opens no devices, saves
    no audio and applies no gain, pitch processing or routing changes.
    """

    def __init__(self, stream):
        self.stream = stream
        self._packet = np.empty(stream.frames, dtype=np.float32)
        self._filled = 0

    def process(self, capture):
        try:
            capture = np.asarray(capture)
        except (TypeError, ValueError):
            self.stream.abort("Invalid capture array")
            raise ValueError("Expected a mono capture array") from None
        if capture.ndim != 1 or not 0 < len(capture) <= self.stream.buffer.capacity:
            self.stream.abort("Invalid mono callback size or channel shape")
            raise ValueError("Expected a bounded nonempty mono callback")
        if (not np.issubdtype(capture.dtype, np.number) or np.iscomplexobj(capture)
                or not np.isfinite(capture).all()):
            self._filled = 0
            self.stream.abort("Invalid capture samples")
            return np.zeros(len(capture), dtype=np.float32)
        if not self.stream.status()["ready"]:
            self._filled = 0
            return np.zeros(len(capture), dtype=np.float32)
        offset = 0
        while offset < len(capture):
            count = min(len(capture) - offset, len(self._packet) - self._filled)
            self._packet[self._filled:self._filled + count] = capture[offset:offset + count]
            self._filled += count
            offset += count
            if self._filled == len(self._packet):
                self._filled = 0
                if not self.stream.submit(self._packet):
                    return np.zeros(len(capture), dtype=np.float32)
        return self.stream.read(len(capture))
