import sys
from pathlib import Path
import tempfile
import unittest
from dataclasses import replace, FrozenInstanceError

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'app'))
from rvc_host_profile import RvcHostProfile


class ProfileContracts(unittest.TestCase):
    def test_explicit_fixed_options_and_no_preference_writes(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            for name in ('snapshot', 'rvc', 'ort', 'ov'):
                (root / name).mkdir()
            (root / 'python.exe').touch()
            (root / 'snapshot/provenance.json').write_text('{}')
            profile = RvcHostProfile(root / 'python.exe', root / 'snapshot',
                                    root / 'rvc', root / 'ort', root / 'ov', root / 'worker.log')
            before = sorted(str(p) for p in root.rglob('*'))
            options = profile.worker_options()
            self.assertEqual((options['startup_packets'], options['max_packets']), (2, 3))
            self.assertFalse(options['recover_underflow'])
            self.assertFalse(options['disable_execution_throttling'])
            self.assertEqual(options['synthesis_backend'], 'openvino')
            larger = replace(profile, startup_ms=600).worker_options()
            self.assertEqual((larger['startup_packets'], larger['max_packets']), (3, 4))
            experimental = replace(profile, startup_ms=1000).worker_options()
            self.assertEqual((experimental['startup_packets'], experimental['max_packets']), (5, 6))
            self.assertFalse(experimental['recover_underflow'])
            self.assertEqual(profile.startup_ms, 400)
            self.assertEqual(before, sorted(str(p) for p in root.rglob('*')))
            with self.assertRaises(FrozenInstanceError):
                profile.pitch = 0
            for invalid in (replace(profile, pitch=float('nan')),
                            replace(profile, python=root / 'missing.exe'),
                            replace(profile, startup_ms=800),
                            replace(profile, log_file=root / 'snapshot/settings.json')):
                with self.assertRaises(ValueError):
                    invalid.worker_options()

if __name__ == '__main__':
    unittest.main()
