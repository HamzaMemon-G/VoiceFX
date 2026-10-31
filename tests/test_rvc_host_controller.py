import sys
from pathlib import Path
from types import SimpleNamespace
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'app'))
from rvc_host_controller import RvcHostController


class ControllerContracts(unittest.TestCase):
    def setup_host(self, ready=True):
        events = []
        class Session:
            def __enter__(self):
                events.append('session')
                return self
            def __exit__(self, *args):
                events.append('worker-close')
            def status(self):
                return dict(state='ready' if ready else 'initializing', ready=ready)
        controller = RvcHostController(Session)
        profile = SimpleNamespace(start=lambda s: events.append('worker-start'))
        return controller, profile, events

    def test_driver_failure_closes_worker(self):
        controller, profile, events = self.setup_host()
        def fail(callback):
            events.append('driver-failed')
            raise RuntimeError('driver unavailable')
        controller.run(profile, fail, RuntimeError)
        self.assertEqual(events, ['session', 'worker-start', 'driver-failed', 'worker-close'])
        self.assertEqual(controller.error, 'driver unavailable')

    def test_driver_closed_before_worker(self):
        controller, profile, events = self.setup_host()
        class Driver:
            def __enter__(self):
                events.append('driver-start')
                controller.stop.set()
            def __exit__(self, *args):
                events.append('driver-close')
        controller.run(profile, lambda cb: Driver(), RuntimeError)
        self.assertEqual(events[-2:], ['driver-close', 'worker-close'])

    def test_not_ready_timeout_never_constructs_driver(self):
        controller, profile, events = self.setup_host(False)
        controller.run(profile, lambda cb: self.fail('driver constructed'), RuntimeError,
                       startup_timeout=0)
        self.assertIn('timed out', controller.error)
        self.assertEqual(events[-1], 'worker-close')

    def test_stopped_controller_cannot_start_duplicate_worker(self):
        controller, profile, events = self.setup_host()
        controller.stop.set()
        controller.run(profile, lambda cb: self.fail('driver constructed'), RuntimeError)
        self.assertNotIn('worker-start', events)
        with self.assertRaises(RuntimeError):
            controller.run(profile, None, RuntimeError)

if __name__ == '__main__':
    unittest.main()
