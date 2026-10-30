"""Host ownership and cancellation without models or audio devices."""
import sys
from pathlib import Path
from threading import Event, Thread
import unittest

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "app"))
from rvc_host_session import RvcHostSession
from test_rvc_capture_bridge import ImmediateStream


class OwnedStream(ImmediateStream):
    def __init__(self):
        super().__init__()
        self.close_count = 0

    def close(self):
        self.close_count += 1
        self.ready = False


class HostContracts(unittest.TestCase):
    def test_monitor_toggle_cannot_change_game_output(self):
        stream = OwnedStream()
        with RvcHostSession() as session:
            session.start(lambda: stream)
            for enabled in (False, True, False, True):
                session.monitor.enabled = enabled
                capture = np.arange(4, dtype=np.float32)
                output = session.process(capture)
                np.testing.assert_array_equal(output, capture)
                headphones = np.empty((4, 1), dtype=np.float32)
                session.monitor.callback(headphones, 4, None, None)
                np.testing.assert_array_equal(headphones[:, 0], capture if enabled else np.zeros(4))
            self.assertEqual(len(stream.submitted), 4)

    def test_factory_failure_stops_session(self):
        session = RvcHostSession()
        def fail():
            raise RuntimeError("startup failed")
        with self.assertRaisesRegex(RuntimeError, "startup failed"):
            session.start(fail)
        self.assertEqual(session.status()["state"], "stopped")
        self.assertFalse(session.process(np.ones(4)).any())

    def test_stop_during_callback_suppresses_returned_audio(self):
        stream = OwnedStream()
        session = RvcHostSession()
        session.start(lambda: stream)
        class ClosingBridge:
            def process(self, capture):
                session.close()
                return np.ones(len(capture))
        session._bridge = ClosingBridge()
        self.assertFalse(session.process(np.ones(4)).any())
        self.assertEqual(stream.close_count, 1)

    def test_stop_during_factory_closes_late_worker(self):
        entered, release = Event(), Event()
        stream = OwnedStream()
        session = RvcHostSession()
        def factory():
            entered.set()
            self.assertTrue(release.wait(2))
            return stream
        thread = Thread(target=session.start, args=(factory,))
        thread.start()
        self.assertTrue(entered.wait(2))
        session.close()
        release.set()
        thread.join(2)
        self.assertFalse(thread.is_alive())
        self.assertEqual(stream.close_count, 1)
        self.assertFalse(session.process(np.ones(4)).any())

    def test_host_failure_closes_once_and_does_not_restart(self):
        stream = OwnedStream()
        with self.assertRaisesRegex(RuntimeError, "device failed"):
            with RvcHostSession() as session:
                session.start(lambda: stream)
                raise RuntimeError("device failed")
        session.close()
        self.assertEqual(stream.close_count, 1)
        with self.assertRaises(RuntimeError):
            session.start(lambda: stream)

    def test_single_packetizer_and_fault_silence(self):
        stream = OwnedStream()
        with RvcHostSession() as session:
            session.start(lambda: stream)
            np.testing.assert_array_equal(session.process(np.arange(4)), np.arange(4))
            self.assertEqual(len(stream.submitted), 1)
            stream.abort("worker failed")
            self.assertFalse(session.process(np.ones(4)).any())
            self.assertEqual(len(stream.submitted), 1)


if __name__ == "__main__":
    unittest.main()
