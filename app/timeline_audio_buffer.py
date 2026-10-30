"""Experimental bounded playout recovery; every missing sample is counted.

This is not a CPU speed fix or a zero-dropout reliability pass. It is never the
default. Late audio is discarded at its original sample position rather than
played back with growing delay. Model/transport corruption still latches silence.
"""

from threading import Lock

import numpy as np

from stream_buffer import StreamFault


class TimelineAudioBuffer:
    def __init__(self, packet_frames, sample_rate, *, startup_packets, max_packets):
        if any(type(v) is not int or v <= 0 for v in
               (packet_frames, sample_rate, startup_packets, max_packets)):
            raise ValueError("Buffer sizes and rate must be positive integers")
        if startup_packets > max_packets:
            raise ValueError("Startup buffering exceeds capacity")
        self.packet_frames = packet_frames
        self.sample_rate = sample_rate
        self.capacity = packet_frames * max_packets
        self._max_packets = max_packets
        self._startup_frames = packet_frames * startup_packets
        self._lock = Lock()
        self._packets = {}
        self._sequence = self._cursor = 0
        self._playing = False
        self._fault = None
        self._missing = self._late = self._events = 0

    def _abort(self, reason):
        if self._fault is None:
            self._fault = str(reason)
        self._packets.clear()

    def abort(self, reason):
        with self._lock:
            self._abort(reason)

    def push(self, sequence, audio):
        try:
            packet = np.array(audio, dtype=np.float32, copy=True)
        except (TypeError, ValueError, OverflowError):
            self.abort("Invalid converted audio")
            raise StreamFault("Invalid converted audio") from None
        with self._lock:
            reason = None
            if self._fault:
                raise StreamFault(self._fault)
            if type(sequence) is not int or sequence != self._sequence:
                reason = "Converted audio packet missing or out of order"
            elif packet.shape != (self.packet_frames,) or not np.isfinite(packet).all():
                reason = "Invalid converted audio"
            if reason:
                self._abort(reason)
                raise StreamFault(reason)
            self._sequence += 1
            start = sequence * self.packet_frames
            expired = max(0, min(self.packet_frames, self._cursor - start)) if self._playing else 0
            self._late += expired
            if expired == self.packet_frames:
                return
            if len(self._packets) >= self._max_packets:
                self._abort("Converted audio queue overflow")
                raise StreamFault(self._fault)
            self._packets[sequence] = packet

    def read(self, frames):
        if type(frames) is not int or not 0 < frames <= self.capacity:
            raise ValueError("Invalid output callback size")
        output = np.zeros(frames, dtype=np.float32)
        with self._lock:
            if self._fault:
                return output
            if not self._playing:
                if len(self._packets) * self.packet_frames < self._startup_frames:
                    return output
                self._playing = True
            written = missing = 0
            while written < frames:
                sequence, offset = divmod(self._cursor, self.packet_frames)
                count = min(frames - written, self.packet_frames - offset)
                packet = self._packets.get(sequence)
                if packet is None:
                    missing += count
                else:
                    output[written:written + count] = packet[offset:offset + count]
                written += count
                self._cursor += count
                if offset + count == self.packet_frames:
                    self._packets.pop(sequence, None)
            self._missing += missing
            self._events += int(missing > 0)
        return output

    def status(self):
        with self._lock:
            buffered = sum(max(0, (seq + 1) * self.packet_frames
                               - max(self._cursor, seq * self.packet_frames))
                           for seq in self._packets)
            return dict(state="fault" if self._fault else ("playing" if self._playing else "buffering"),
                fault=self._fault, buffered_frames=buffered,
                buffered_ms=1000 * buffered / self.sample_rate,
                startup_audio_ms=1000 * self._startup_frames / self.sample_rate,
                recovery_mode=True, missing_samples=self._missing,
                underflow_events=self._events, late_discarded_samples=self._late,
                playout_frames=self._cursor,
                warning="Experimental dropout recovery, not zero-loss validation; queue duration excludes capture, compute, alignment and hardware delay")
