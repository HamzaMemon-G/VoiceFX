"""Real local-pipe lifecycle/backpressure tests using a tiny fake worker."""

from pathlib import Path
import sys
import tempfile
import time
import unittest
from unittest.mock import patch

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "app"))
from rvc_process import RvcProcessStream


class ProcessContracts(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.root = Path(self.directory.name)
        self.stream = None

    def tearDown(self):
        if self.stream:
            self.stream.close()
        self.directory.cleanup()

    def create(self, mode="normal", capacity=3, conversion_timeout=2, dynamic=0):
        service = self.root / "fake_service.py"
        service.write_text('''import json,sys,time
mode=MODE
dynamic=int(sys.argv[sys.argv.index('--dynamic-block-base')+1])
time.sleep(10 if mode=='slow_start' else .1)
print(json.dumps(dict(type='ready',frames=9600,sample_rate=48000,dynamic_block_base=0 if mode=='bad_schedule' else dynamic)),flush=True)
for line in sys.stdin:
 m=json.loads(line)
 if m['type']=='stop':break
 if mode=='slow':time.sleep(.5)
 sequence=m['sequence']+(1 if mode=='bad_order' else 0)
 print(json.dumps(dict(type='converted',sequence=sequence,audio=m['audio'],compute_ms=1.0)),flush=True)
'''.replace("MODE", repr(mode)))
        with patch("rvc_process.SERVICE_PATH", service):
            self.stream = RvcProcessStream(sys.executable, "unused", "unused", "unused",
                self.root / "worker.log", startup_packets=1, max_packets=capacity,
                startup_timeout=15, conversion_timeout=conversion_timeout,
                dynamic_block_base=dynamic)
        return self.stream

    def wait(self, predicate, timeout=5):
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if predicate():
                return
            time.sleep(.01)
        self.fail(f"Timed out; stream status: {self.stream.status()}")

    def test_startup_pipe_and_fragmented_callbacks_preserve_audio(self):
        stream = self.create()
        self.assertFalse(stream.submit(np.zeros(9600)))
        self.assertFalse(stream.read(960).any())
        self.wait(lambda: stream.status()["ready"])
        audio = np.linspace(-.5, .5, 9600, dtype=np.float32)
        self.assertTrue(stream.submit(audio))
        self.wait(lambda: stream.status()["buffered_frames"] == 9600)
        output = np.concatenate((stream.read(4096), stream.read(5504)))
        np.testing.assert_array_equal(output, audio)
        metrics = stream.metrics()
        self.assertEqual(len(metrics), 1)
        self.assertEqual(metrics[0]["sequence"], 0)
        self.assertGreaterEqual(metrics[0]["roundtrip_ms"], 0)
        self.assertNotIn("audio", metrics[0])
        stream.close()
        self.assertIsNotNone(stream._process.poll())

    def test_bad_sequence_stops_with_silence(self):
        stream = self.create("bad_order")
        self.wait(lambda: stream.status()["ready"])
        self.assertTrue(stream.submit(np.ones(9600)))
        self.wait(lambda: stream.status()["state"] == "fault")
        self.assertFalse(stream.read(9600).any())
        self.assertFalse(stream.submit(np.ones(9600)))

    def test_experimental_scheduling_requires_matching_acknowledgement(self):
        stream = self.create(dynamic=4)
        self.wait(lambda: stream.status()["ready"])
        self.assertEqual(stream.status()["experimental_dynamic_block_base"], 4)
        stream.close()
        stream = self.create("bad_schedule", dynamic=4)
        self.wait(lambda: stream.status()["state"] == "fault")
        self.assertFalse(stream.status()["ready"])

    def test_slow_worker_has_bounded_input_and_output(self):
        stream = self.create("slow", capacity=1)
        self.wait(lambda: stream.status()["ready"])
        results = [stream.submit(np.ones(9600)) for _ in range(6)]
        self.assertIn(False, results)
        self.assertLessEqual(stream.status()["queued_input_packets"], 1)
        self.assertEqual(stream.status()["state"], "fault")
        self.assertFalse(stream.read(9600).any())

    def test_conversion_timeout_and_early_startup_close(self):
        stream = self.create("slow", conversion_timeout=.1)
        self.wait(lambda: stream.status()["ready"])
        stream.submit(np.ones(9600))
        self.wait(lambda: stream.status()["state"] == "fault")
        stream.close()
        self.assertIsNotNone(stream._process.poll())
        stream = self.create("slow_start")
        self.wait(lambda: stream._process is not None)
        stream.close()
        self.assertIsNotNone(stream._process.poll())
        self.assertFalse(stream.status()["ready"])


if __name__ == "__main__":
    unittest.main()
