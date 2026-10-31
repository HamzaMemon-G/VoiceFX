"""No driver or model imports: callback output, mute and failure contracts."""
import sys
from pathlib import Path
from threading import Event
from types import SimpleNamespace
import unittest
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'app'))
from rvc_host_callback import RvcHostCallback
from rvc_host_session import RvcHostSession
from test_rvc_host_session import OwnedStream

class StopCallback(Exception):
    pass

class CallbackContracts(unittest.TestCase):
    def test_failed_render_leaves_silence_and_requests_host_cleanup(self):
        for result in (RuntimeError('worker gone'), np.array([np.nan] * 4), np.ones(3)):
            class FailedSession:
                def status(self):
                    return {'state': 'ready'}
                def process(self, *args, **kwargs):
                    if isinstance(result, Exception):
                        raise result
                    return result
            stop = Event()
            callback = RvcHostCallback(FailedSession(), stop, StopCallback)
            output = np.ones((4, 1), dtype=np.float32)
            callback(np.ones((4, 1)), output, 4, None,
                     SimpleNamespace(input_overflow=False, output_underflow=False))
            self.assertTrue(stop.is_set())
            self.assertFalse(output.any())
            self.assertIn('Voice callback failed', callback.error)

    def test_volume_and_mute_match_headphone_and_game_destinations(self):
        stream = OwnedStream()
        with RvcHostSession() as session:
            session.start(lambda: stream)
            session.monitor.enabled = True
            callback = RvcHostCallback(session, Event(), StopCallback)
            callback.volume = .5
            for muted in (False, True):
                callback.mute = muted
                output = np.ones((4, 2), dtype=np.float32)
                callback(np.ones((4, 1), dtype=np.float32), output, 4, None,
                         SimpleNamespace(input_overflow=False, output_underflow=False))
                np.testing.assert_array_equal(output, np.full((4, 2), 0 if muted else .5))
                headphones = np.empty((4, 1), dtype=np.float32)
                session.monitor.callback(headphones, 4, None, None)
                np.testing.assert_array_equal(headphones[:, 0], output[:, 0])

    def test_driver_fault_stops_without_submitting_capture(self):
        stream = OwnedStream()
        with RvcHostSession() as session:
            session.start(lambda: stream)
            stop = Event()
            callback = RvcHostCallback(session, stop, StopCallback)
            output = np.ones((4, 1), dtype=np.float32)
            callback(np.ones((4, 1)), output, 4, None,
                     SimpleNamespace(input_overflow=True, output_underflow=False))
            self.assertFalse(output.any())
            self.assertEqual(stream.submitted, [])
            self.assertTrue(stop.is_set())
            with self.assertRaises(StopCallback):
                callback(np.ones((4, 1)), output, 4, None, None)

if __name__ == '__main__':
    unittest.main()
