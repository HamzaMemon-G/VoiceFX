"""Offline worker/audio callback contracts; no devices or models are opened."""

import sys
import unittest
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "app"))
from stream_buffer import PacketAudioBuffer, StreamFault


class BufferContracts(unittest.TestCase):
    def make(self, startup=2, capacity=3):
        return PacketAudioBuffer(4, 1000, startup_packets=startup, max_packets=capacity)

    def test_startup_and_fragmented_callbacks_preserve_every_sample(self):
        buffer = self.make()
        first = np.arange(4, dtype=np.float32)
        buffer.push(0, first)
        first[:] = -100  # Producer reuse must not change published samples.
        np.testing.assert_array_equal(buffer.read(3), np.zeros(3))
        self.assertEqual(buffer.status()["buffered_frames"], 4)
        buffer.push(1, np.arange(4, 8))
        a = buffer.read(3)
        buffer.push(2, np.arange(8, 12))
        b = buffer.read(5)
        c = buffer.read(4)
        np.testing.assert_array_equal(np.concatenate((a, b, c)), np.arange(12))

    def test_underflow_latches_silence_instead_of_replaying_late_audio(self):
        buffer = self.make(startup=1)
        buffer.push(0, np.ones(4))
        np.testing.assert_array_equal(buffer.read(3), np.ones(3))
        np.testing.assert_array_equal(buffer.read(2), np.zeros(2))
        self.assertEqual(buffer.status()["state"], "fault")
        with self.assertRaises(StreamFault):
            buffer.push(1, np.ones(4))
        np.testing.assert_array_equal(buffer.read(2), np.zeros(2))

    def test_overflow_is_bounded_and_stops_output(self):
        buffer = self.make(capacity=2)
        buffer.push(0, np.ones(4))
        buffer.push(1, np.ones(4))
        with self.assertRaisesRegex(StreamFault, "overflow"):
            buffer.push(2, np.ones(4))
        self.assertEqual(buffer.status()["buffered_frames"], 0)
        np.testing.assert_array_equal(buffer.read(4), np.zeros(4))

    def test_missing_packet_and_invalid_model_output_stop_playback(self):
        for sequence, packet in [(1, np.ones(4)), (0, np.ones(3)),
                                 (0, [1, 2, 3, np.nan]), (0, [object()])]:
            with self.subTest(sequence=sequence, packet=packet):
                buffer = self.make()
                with self.assertRaises(StreamFault):
                    buffer.push(sequence, packet)
                np.testing.assert_array_equal(buffer.read(4), np.zeros(4))

    def test_duration_is_queue_audio_only(self):
        buffer = self.make()
        self.assertEqual(buffer.status()["startup_audio_ms"], 8)
        self.assertEqual(buffer.status()["buffered_ms"], 0)
        with self.assertRaises(ValueError):
            PacketAudioBuffer(4, 1000, startup_packets=3, max_packets=2)


if __name__ == "__main__":
    unittest.main()
