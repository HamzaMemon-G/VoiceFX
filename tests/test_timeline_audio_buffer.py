"""Recovery is explicit sample loss, never an unreported latency increase."""

from pathlib import Path
import sys
import unittest

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "app"))
from stream_buffer import StreamFault
from timeline_audio_buffer import TimelineAudioBuffer


class TimelineContracts(unittest.TestCase):
    def make(self, startup=1, capacity=3):
        return TimelineAudioBuffer(4, 1000, startup_packets=startup, max_packets=capacity)

    def test_healthy_callbacks_preserve_every_sample(self):
        buffer = self.make()
        buffer.push(0, np.arange(4))
        buffer.push(1, np.arange(4, 8))
        output = [buffer.read(3), buffer.read(2)]
        buffer.push(2, np.arange(8, 12))
        output.append(buffer.read(7))
        np.testing.assert_array_equal(np.concatenate(output), np.arange(12))
        self.assertEqual(buffer.status()["missing_samples"], 0)

    def test_partial_late_packet_is_trimmed_without_replaying_lost_time(self):
        buffer = self.make()
        buffer.push(0, [10, 11, 12, 13])
        np.testing.assert_array_equal(buffer.read(4), [10, 11, 12, 13])
        np.testing.assert_array_equal(buffer.read(2), [0, 0])
        buffer.push(1, [20, 21, 22, 23])
        np.testing.assert_array_equal(buffer.read(2), [22, 23])
        self.assertEqual(buffer.status()["missing_samples"], 2)
        self.assertEqual(buffer.status()["late_discarded_samples"], 2)
        self.assertEqual(buffer.status()["underflow_events"], 1)
        self.assertEqual(buffer.status()["playout_frames"], 8)

    def test_fully_late_packet_does_not_accumulate_delay(self):
        buffer = self.make()
        buffer.push(0, np.ones(4))
        buffer.read(4)
        buffer.read(4)
        buffer.push(1, np.full(4, 99))
        self.assertEqual(buffer.status()["buffered_frames"], 0)
        buffer.push(2, np.arange(4))
        np.testing.assert_array_equal(buffer.read(4), np.arange(4))
        self.assertEqual(buffer.status()["missing_samples"], 4)
        self.assertEqual(buffer.status()["late_discarded_samples"], 4)

    def test_startup_silence_does_not_start_the_loss_clock(self):
        buffer = self.make(startup=2)
        buffer.read(3)
        buffer.push(0, np.arange(4))
        buffer.read(3)
        self.assertEqual(buffer.status()["playout_frames"], 0)
        self.assertEqual(buffer.status()["missing_samples"], 0)
        buffer.push(1, np.arange(4, 8))
        np.testing.assert_array_equal(buffer.read(6), np.arange(6))

    def test_corruption_and_capacity_overflow_still_latch_a_fault(self):
        buffer = self.make(capacity=2)
        buffer.push(0, np.ones(4))
        buffer.push(1, np.ones(4))
        with self.assertRaises(StreamFault):
            buffer.push(2, np.ones(4))
        self.assertEqual(buffer.status()["state"], "fault")
        np.testing.assert_array_equal(buffer.read(4), np.zeros(4))
        for sequence, values in [(1, np.ones(4)), (0, [1, 2, 3, np.nan])]:
            with self.assertRaises(StreamFault):
                self.make().push(sequence, values)


if __name__ == "__main__":
    unittest.main()
