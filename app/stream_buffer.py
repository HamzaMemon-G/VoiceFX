"""Bounded audio handoff for an optional conversion worker.

This module opens no devices and changes no routing. It is not enabled by the
application yet. A host must explicitly choose its startup buffering, account
for that delay, and validate its converter's sustained performance.
"""

from collections import deque
from threading import Lock

import numpy as np


class StreamFault(RuntimeError):
    pass


class PacketAudioBuffer:
    """Preserve ordered converted samples; latch silence on a stream fault.

    Startup reads return silence without consuming queued speech. After playback
    starts, underflow, overflow, invalid output or missing packets stop playback.
    A fresh instance is required to restart, preventing an unnoticed delay jump.
    No inference, waiting, file access or device operation occurs in ``read``.
    """

    def __init__(self, packet_frames, sample_rate, *, startup_packets, max_packets):
        values = (packet_frames, sample_rate, startup_packets, max_packets)
        if any(type(value) is not int or value <= 0 for value in values):
            raise ValueError("Buffer sizes and sample rate must be positive integers")
        if startup_packets > max_packets:
            raise ValueError("Startup buffering exceeds capacity")
        self.packet_frames = packet_frames
        self.sample_rate = sample_rate
        self.capacity = packet_frames * max_packets
        self.startup_frames = packet_frames * startup_packets
        self._lock = Lock()
        self._packets = deque()
        self._offset = self._frames = self._sequence = 0
        self._playing = False
        self._fault = None

    def _stop(self, reason):
        self._fault = reason
        self._packets.clear()
        self._frames = self._offset = 0
        raise StreamFault(reason)

    def push(self, sequence, audio):
        # Copy before publishing: the producer may reuse its inference buffer.
        try:
            packet = np.array(audio, dtype=np.float32, copy=True)
        except (TypeError, ValueError, OverflowError):
            with self._lock:
                self._stop("Invalid converted audio")
        with self._lock:
            if self._fault:
                raise StreamFault(self._fault)
            if type(sequence) is not int or sequence != self._sequence:
                self._stop("Converted audio packet missing or out of order")
            if packet.shape != (self.packet_frames,) or not np.isfinite(packet).all():
                self._stop("Invalid converted audio")
            if self._frames + self.packet_frames > self.capacity:
                self._stop("Converted audio queue overflow")
            self._packets.append(packet)
            self._frames += self.packet_frames
            self._sequence += 1

    def read(self, frames):
        if type(frames) is not int or not 0 < frames <= self.capacity:
            raise ValueError("Invalid output callback size")
        output = np.zeros(frames, dtype=np.float32)
        with self._lock:
            if self._fault:
                return output
            if not self._playing:
                if self._frames < self.startup_frames:
                    return output
                self._playing = True
            if self._frames < frames:
                try:
                    self._stop("Converted audio queue underflow")
                except StreamFault:
                    return output
            written = 0
            while written < frames:
                packet = self._packets[0]
                count = min(frames - written, self.packet_frames - self._offset)
                output[written:written + count] = packet[self._offset:self._offset + count]
                self._offset += count
                self._frames -= count
                written += count
                if self._offset == self.packet_frames:
                    self._packets.popleft()
                    self._offset = 0
        return output

    def status(self):
        with self._lock:
            return {
                "state": "fault" if self._fault else ("playing" if self._playing else "buffering"),
                "fault": self._fault,
                "buffered_frames": self._frames,
                "buffered_ms": 1000 * self._frames / self.sample_rate,
                "startup_audio_ms": 1000 * self.startup_frames / self.sample_rate,
                "warning": "Queue duration excludes capture, inference, model alignment and hardware delay",
            }

    def abort(self, reason):
        """Latch a worker/transport fault without raising in a callback."""
        with self._lock:
            if self._fault is None:
                self._fault = str(reason)
            self._packets.clear()
            self._frames = self._offset = 0
