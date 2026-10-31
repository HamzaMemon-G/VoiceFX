import contextlib
import io
import sys
from pathlib import Path
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'app'))
from rvc_experimental_session import main


class EntryContracts(unittest.TestCase):
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
