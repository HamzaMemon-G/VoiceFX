import contextlib
import io
import sys
from pathlib import Path
import unittest
from unittest.mock import patch
from types import SimpleNamespace
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'app'))
from rvc_experimental_session import main
from test_rvc_host_driver import FakeSoundDevice
from test_rvc_host_session import OwnedStream


class EntryContracts(unittest.TestCase):
    def test_existing_session_rejects_before_worker_or_driver(self):
        profile = SimpleNamespace(worker_options=lambda: {})
        with patch('rvc_experimental_session.RvcHostProfile', return_value=profile), \
             patch('windows_resource_guard.active_games', return_value=[]), \
             patch.dict(sys.modules, {'sounddevice': SimpleNamespace(CallbackStop=RuntimeError)}), \
             patch('rvc_experimental_session.VoiceSessionLock') as lock, \
             patch('rvc_experimental_session.RvcHostController') as controller, \
             patch('rvc_experimental_session.Timer') as timer, \
             contextlib.redirect_stdout(io.StringIO()):
            lock.return_value.__enter__.side_effect = RuntimeError('Another VoiceFX session')
            self.assertEqual(main(self.args() + ['--start']), 2)
            controller.return_value.run.assert_not_called()
            timer.return_value.cancel.assert_called_once()

    def test_full_opt_in_entrypoint_with_synthetic_devices_and_worker(self):
        stream = OwnedStream()
        output = []
        class Devices(FakeSoundDevice):
            CallbackStop = RuntimeError
            def Stream(self, **options):
                callback = options['callback']
                base = self.make('duplex', options)
                class Driver:
                    active = True
                    def __enter__(self):
                        base.__enter__()
                        rendered = np.empty((4, 2), dtype=np.float32)
                        callback(np.ones((4, 1), dtype=np.float32), rendered, 4, None,
                            SimpleNamespace(input_overflow=False, output_underflow=False))
                        output.append(rendered.copy())
                        callback.stop.set()
                        return self
                    def __exit__(self, *exc):
                        base.__exit__(*exc)
                return Driver()
        sd = Devices()
        profile = SimpleNamespace(worker_options=lambda: {},
            start=lambda session: session.start(lambda: stream))
        args = self.args() + ['--start', '--input-name', 'Mic', '--output-name', 'Game']
        with patch('rvc_experimental_session.RvcHostProfile', return_value=profile), \
             patch('windows_resource_guard.active_games', return_value=[]), \
             patch.dict(sys.modules, {'sounddevice': sd}), \
             patch('rvc_experimental_session.VoiceSessionLock'), \
             patch('rvc_experimental_session.Timer') as timer, \
             contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(main(args), 0)
        np.testing.assert_array_equal(output[0], np.ones((4, 2)))
        self.assertEqual(stream.close_count, 1)
        self.assertEqual(sd.calls[-1], ('close', 'duplex'))
        timer.return_value.cancel.assert_called_once()

    def args(self):
        return [part for name in ('python', 'snapshot', 'rvc-root', 'ort-packages',
                                 'openvino-packages', 'log-file', 'input-name', 'output-name')
                for part in ('--' + name, 'explicit')]
    def test_no_start_rejects_before_runtime_or_device_access(self):
        with patch('rvc_experimental_session.RvcHostProfile') as profile:
            with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
                main(self.args())
            profile.assert_not_called()
    def test_invalid_monitor_or_duration_rejects_before_runtime(self):
        for extra in (['--hear-myself'], ['--seconds', '0']):
            with patch('rvc_experimental_session.RvcHostProfile') as profile:
                with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
                    main(self.args() + ['--start'] + extra)
                profile.assert_not_called()

if __name__ == '__main__':
    unittest.main()
