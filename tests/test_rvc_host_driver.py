import sys
from pathlib import Path
from types import SimpleNamespace
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'app'))
from rvc_host_driver import explicit_driver


class FakeSoundDevice:
    def __init__(self, fail=False):
        self.calls = []
        self.fail = fail
    def query_devices(self):
        return [dict(name=name, hostapi=0, max_input_channels=1 if name == 'Mic' else 0,
                     max_output_channels=0 if name == 'Mic' else 2)
                for name in ('Mic', 'Game', 'Headphones')]
    def query_hostapis(self, index):
        return {'name': 'MME'}
    def OutputStream(self, **options):
        return self.make('monitor', options)
    def Stream(self, **options):
        if self.fail:
            raise RuntimeError('device unavailable')
        return self.make('duplex', options)
    def make(self, name, options):
        owner = self
        class Driver:
            active = True
            def __enter__(self):
                owner.calls.append(('open', name, options))
                return self
            def __exit__(self, *exc):
                owner.calls.append(('close', name))
        return Driver()


class DriverContracts(unittest.TestCase):
    def callback(self):
        return SimpleNamespace(session=SimpleNamespace(monitor=SimpleNamespace(callback=lambda *a: None)))
    def test_explicit_indices_channels_and_cleanup(self):
        sd = FakeSoundDevice()
        with explicit_driver(sd, self.callback(), input_name='Mic', output_name='Game', monitor_name='Headphones'):
            self.assertEqual(sd.calls[1][2]['device'], (0, 1))
            self.assertEqual(sd.calls[1][2]['blocksize'], 960)
        self.assertEqual(sd.calls[-2:], [('close', 'duplex'), ('close', 'monitor')])
    def test_rejects_missing_or_same_monitor_before_open(self):
        for inp, monitor in [('', ''), ('Missing', ''), ('Mic', 'Game')]:
            sd = FakeSoundDevice()
            with self.assertRaises(ValueError):
                with explicit_driver(sd, self.callback(), input_name=inp, output_name='Game', monitor_name=monitor):
                    self.fail('opened invalid selection')
            self.assertEqual(sd.calls, [])
    def test_duplex_failure_closes_monitor(self):
        sd = FakeSoundDevice(fail=True)
        with self.assertRaises(RuntimeError):
            with explicit_driver(sd, self.callback(), input_name='Mic', output_name='Game', monitor_name='Headphones'):
                self.fail('opened failed device')
        self.assertEqual(sd.calls[-1], ('close', 'monitor'))
    def test_duplicate_names_never_fall_back_to_first(self):
        sd = FakeSoundDevice()
        devices = sd.query_devices()
        sd.query_devices = lambda: devices + [devices[0].copy()]
        with self.assertRaises(ValueError):
            with explicit_driver(sd, self.callback(), input_name='Mic', output_name='Game'):
                self.fail('ambiguous device opened')
        self.assertEqual(sd.calls, [])

if __name__ == '__main__':
    unittest.main()
