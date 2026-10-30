"""Real local-pipe lifecycle/backpressure tests using a tiny fake worker."""

from pathlib import Path
import sys
import os
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

    def create(self, mode="normal", capacity=3, conversion_timeout=2, dynamic=0,
               synthesis_backend="ort", worker_priority="normal", recover=False):
        service = self.root / "fake_service.py"
        service.write_text('''import json,sys,time,subprocess
from pathlib import Path
mode=MODE
dynamic=int(sys.argv[sys.argv.index('--dynamic-block-base')+1])
backend=sys.argv[sys.argv.index('--synthesis-backend')+1]
time.sleep(10 if mode=='slow_start' else .1)
if mode=='descendant_holds_pipe':
 child=subprocess.Popen([sys.executable,'-c','import time;time.sleep(60)'],stdout=sys.stdout,stderr=sys.stderr,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
 Path(sys.argv[0]).with_suffix('.childpid').write_text(str(child.pid))
print(json.dumps(dict(type='ready',frames=9600,sample_rate=48000,dynamic_block_base=0 if mode=='bad_schedule' else dynamic,synthesis_backend='ort' if mode=='bad_backend' else backend)),flush=True)
if mode=='exit_idle':raise SystemExit(0)
for line in sys.stdin:
 m=json.loads(line)
 if m['type']=='stop':break
 if mode=='slow':time.sleep(.5)
 if mode=='hang_convert':time.sleep(60)
 sequence=m['sequence']+(1 if mode=='bad_order' else 0)
 print(json.dumps(dict(type='converted',sequence=sequence,audio=m['audio'],compute_ms=1.0)),flush=True)
'''.replace("MODE", repr(mode)))
        with patch("rvc_process.SERVICE_PATH", service):
            self.stream = RvcProcessStream(sys.executable, "unused", "unused", "unused",
                self.root / "worker.log", startup_packets=1, max_packets=capacity,
                startup_timeout=15, conversion_timeout=conversion_timeout,
                dynamic_block_base=dynamic, synthesis_backend=synthesis_backend,
                openvino_packages=self.root if synthesis_backend == "openvino" else None,
                worker_priority=worker_priority, recover_underflow=recover)
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

    def test_idle_worker_exit_clears_readiness_without_new_capture(self):
        stream = self.create("exit_idle")
        self.wait(lambda: stream.status()["state"] == "fault")
        self.assertFalse(stream.status()["ready"])
        self.assertFalse(stream.read(9600).any())

    def test_experimental_scheduling_requires_matching_acknowledgement(self):
        stream = self.create(dynamic=4)
        self.wait(lambda: stream.status()["ready"])
        self.assertEqual(stream.status()["experimental_dynamic_block_base"], 4)
        stream.close()
        stream = self.create("bad_schedule", dynamic=4)
        self.wait(lambda: stream.status()["state"] == "fault")
        self.assertFalse(stream.status()["ready"])

    def test_synthesis_backend_requires_matching_acknowledgement(self):
        stream = self.create(synthesis_backend="openvino")
        self.wait(lambda: stream.status()["ready"])
        self.assertEqual(stream.status()["experimental_synthesis_backend"], "openvino")
        stream.close()
        stream = self.create("bad_backend", synthesis_backend="openvino")
        self.wait(lambda: stream.status()["state"] == "fault")
        self.assertFalse(stream.status()["ready"])

    @unittest.skipUnless(os.name == "nt", "Windows-only scoped scheduling")
    def test_scoped_priority_applies_only_to_created_worker_and_exits(self):
        stream = self.create(worker_priority="above_normal")
        self.wait(lambda: stream.status()["ready"])
        self.assertEqual(stream.status()["verified_priority_class"], 0x8000)
        stream.close()
        self.assertIsNotNone(stream._process.poll())

    def test_slow_worker_has_bounded_input_and_output(self):
        stream = self.create("slow", capacity=1)
        self.wait(lambda: stream.status()["ready"])
        results = [stream.submit(np.ones(9600)) for _ in range(6)]
        self.assertIn(False, results)
        self.assertLessEqual(stream.status()["queued_input_packets"], 1)
        self.assertEqual(stream.status()["state"], "fault")
        self.assertFalse(stream.read(9600).any())

    def test_explicit_recovery_counts_loss_and_trims_a_late_packet(self):
        stream = self.create("slow", recover=True)
        self.wait(lambda: stream.status()["ready"])
        stream.submit(np.ones(9600))
        self.wait(lambda: stream.status()["buffered_frames"] == 9600)
        stream.read(9600)
        self.assertFalse(stream.read(960).any())
        packet = np.arange(9600, dtype=np.float32)
        stream.submit(packet)
        self.wait(lambda: stream.status()["buffered_frames"] == 8640)
        np.testing.assert_array_equal(stream.read(8640), packet[960:])
        self.assertTrue(stream.status()["ready"])
        self.assertEqual(stream.status()["missing_samples"], 960)
        self.assertEqual(stream.status()["late_discarded_samples"], 960)

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

    @unittest.skipUnless(os.name == 'nt', 'Windows owned worker tree')
    def test_shutdown_closes_descendant_inheriting_stdout(self):
        import ctypes
        from ctypes import wintypes
        stream=self.create('descendant_holds_pipe')
        self.wait(lambda: stream.status()['ready'])
        pid=int((self.root/'fake_service.childpid').read_text())
        kernel=ctypes.WinDLL('kernel32',use_last_error=True)
        kernel.OpenProcess.argtypes=[wintypes.DWORD,wintypes.BOOL,wintypes.DWORD]
        kernel.OpenProcess.restype=wintypes.HANDLE
        kernel.WaitForSingleObject.argtypes=[wintypes.HANDLE,wintypes.DWORD]
        kernel.CloseHandle.argtypes=[wintypes.HANDLE]
        handle=kernel.OpenProcess(0x100000,False,pid)
        self.assertTrue(handle)
        try:
            stream.close()
            self.assertEqual(kernel.WaitForSingleObject(handle,2000),0)
            self.assertFalse(stream._thread.is_alive())
            self.assertFalse(stream._reader_thread.is_alive())
        finally:
            kernel.CloseHandle(handle)

    def test_close_cancels_inflight_receive_and_ends_reader(self):
        stream=self.create('hang_convert',conversion_timeout=30)
        self.wait(lambda: stream.status()['ready'])
        stream.submit(np.ones(9600))
        time.sleep(.1)
        started=time.monotonic()
        stream.close()
        self.assertLess(time.monotonic()-started,6)
        self.assertIsNotNone(stream._process.poll())
        self.assertFalse(stream._reader_thread.is_alive())


if __name__ == "__main__":
    unittest.main()
