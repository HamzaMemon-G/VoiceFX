"""Capture/worker packet boundaries and startup privacy, without devices."""

from pathlib import Path
import sys
import unittest

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "app"))
from rvc_capture_bridge import RvcCaptureBridge
from stream_buffer import PacketAudioBuffer


class ImmediateStream:
    frames = 4

    def __init__(self):
        self.buffer = PacketAudioBuffer(4, 1000, startup_packets=1, max_packets=3)
        self.ready = True
        self.submitted = []

    def submit(self, packet):
        owned = packet.copy()
        self.buffer.push(len(self.submitted), owned)
        self.submitted.append(owned)
        return True

    def read(self, frames):
        return self.buffer.read(frames)

    def status(self):
        return dict(self.buffer.status(), ready=self.ready and self.buffer.status()["state"] != "fault")

    def abort(self, reason):
        self.buffer.abort(reason)


class CaptureContracts(unittest.TestCase):
    def test_nondividing_callback_sizes_preserve_input_and_output_order(self):
        stream = ImmediateStream()
        bridge = RvcCaptureBridge(stream)
        first = bridge.process(np.arange(3, dtype=np.float32))
        np.testing.assert_array_equal(first, np.zeros(3))
        output = [bridge.process(np.arange(3, 6)), bridge.process(np.arange(6, 10)),
                  bridge.process(np.arange(10, 12)), stream.read(3)]
        np.testing.assert_array_equal(np.concatenate(stream.submitted), np.arange(12))
        np.testing.assert_array_equal(np.concatenate(output), np.arange(12))

    def test_pre_ready_capture_is_not_retained_or_submitted(self):
        stream = ImmediateStream()
        bridge = RvcCaptureBridge(stream)
        stream.ready = False
        self.assertFalse(bridge.process(np.ones(3)).any())
        self.assertEqual(stream.submitted, [])
        stream.ready = True
        bridge.process(np.arange(4))
        np.testing.assert_array_equal(stream.submitted[0], np.arange(4))

    def test_invalid_samples_or_channels_stop_without_dry_fallback(self):
        for samples in (np.array([1., np.nan]), np.array([1 + 2j]), np.array(["invalid"])):
            stream = ImmediateStream()
            bridge = RvcCaptureBridge(stream)
            self.assertFalse(bridge.process(samples).any())
            self.assertEqual(stream.status()["state"], "fault")
            self.assertEqual(stream.submitted, [])
        with self.assertRaises(ValueError):
            bridge.process(np.ones((2, 2)))


if __name__ == "__main__":
    unittest.main()
