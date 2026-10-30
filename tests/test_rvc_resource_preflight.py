"""A running game must block diagnostic model loading, not close the game."""
import json
import hashlib
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
from unittest.mock import MagicMock
import numpy as np
from threading import Event

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'app'))
import rvc_cpu_check
import rvc_cpu_fixture_check
from windows_resource_guard import GameLoadWatch


class ResourcePreflight(unittest.TestCase):
    def fixture_startup_case(self,watch_failure=False):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder)
            source=root/'public.wav'
            source.write_bytes(b'public-test-placeholder')
            reference=root/'reference.npy'
            np.save(reference,np.zeros(9600,dtype=np.float32),allow_pickle=False)
            entry=dict(name='one',source=source.name,reference=reference.name,pitch=-9,
                source_sha256=hashlib.sha256(source.read_bytes()).hexdigest(),
                reference_sha256=hashlib.sha256(reference.read_bytes()).hexdigest())
            (root/'manifest.json').write_text(json.dumps(dict(
                preparation='PCM16 mono to48k resample_poly3_1, then zero-pad to9600; no gain/denoise',
                cases=[entry,dict(entry,name='two')])))
            stream=MagicMock()
            stream.status.return_value=dict(ready=False,state='fault',buffered_frames=0)
            stream._thread.is_alive.return_value=False
            watch=MagicMock()
            watch.status.return_value=dict(blocked=True,games=[dict(name='Fortnite',pid=1)],error=None)
            args=['--python',sys.executable,'--fixture',str(root),'--snapshot','unused',
                  '--rvc-root','unused','--ort-packages','unused','--report',str(root/'report.json')]
            with patch.object(rvc_cpu_fixture_check,'active_games',return_value=[]), \
                 patch.object(rvc_cpu_fixture_check,'load_source',return_value=np.zeros(9600,dtype=np.float32)), \
                 patch.object(rvc_cpu_fixture_check,'RvcProcessStream',return_value=stream) as factory, \
                 patch.object(rvc_cpu_fixture_check,'GameLoadWatch',return_value=watch,
                     side_effect=RuntimeError('observer unavailable') if watch_failure else None):
                self.assertEqual(rvc_cpu_fixture_check.main(args),2)
                self.assertEqual(factory.call_count,1)
                stream.close.assert_called_once()
                if not watch_failure:
                    watch.close.assert_called_once()
            result=json.loads((root/'report.json').read_text())
            self.assertTrue(result['resource_blocked'])
            self.assertFalse(result['public_waveform_parity_passed'])
            self.assertEqual(len(result['cases']),1)

    def test_game_during_fixture_startup_closes_worker_and_skips_next_case(self):
        self.fixture_startup_case()

    def test_failed_watch_construction_still_closes_worker(self):
        self.fixture_startup_case(watch_failure=True)

    def test_game_start_aborts_only_supplied_workload_and_stops_watch(self):
        aborted=Event()
        reasons=[]
        def abort(reason):
            reasons.append(reason)
            aborted.set()
        with patch('windows_resource_guard.active_games',return_value=[dict(name='Fortnite',pid=1)]):
            watch=GameLoadWatch(abort)
            try:
                self.assertTrue(aborted.wait(1))
                self.assertTrue(watch.status()['blocked'])
                self.assertEqual(len(reasons),1)
            finally:
                watch.close()

    def test_failed_resource_observation_does_not_assume_idle(self):
        aborted=Event()
        with patch('windows_resource_guard.active_games',side_effect=OSError):
            watch=GameLoadWatch(lambda reason:aborted.set())
            try:
                self.assertTrue(aborted.wait(1))
                self.assertTrue(watch.status()['blocked'])
            finally:
                watch.close()

    def test_timing_check_blocks_before_loading_source_or_worker(self):
        with tempfile.TemporaryDirectory() as folder:
            report=Path(folder)/'check.json'
            args=['--snapshot','unused','--rvc-root','unused','--ort-packages','unused',
                  '--source','unused','--report',str(report)]
            with patch.object(rvc_cpu_check,'active_games',return_value=[dict(name='Fortnite',pid=1)]), \
                 patch.object(rvc_cpu_check,'RvcProcessStream') as worker, \
                 patch.object(rvc_cpu_check,'load_source') as source:
                self.assertEqual(rvc_cpu_check.main(args),2)
                worker.assert_not_called()
                source.assert_not_called()
            self.assertTrue(json.loads(report.read_text())['resource_blocked'])

    def test_fixture_check_blocks_before_reading_manifest_or_worker(self):
        with tempfile.TemporaryDirectory() as folder:
            report=Path(folder)/'fixture.json'
            args=['--python',sys.executable,'--fixture','unused','--snapshot','unused',
                  '--rvc-root','unused','--ort-packages','unused','--report',str(report)]
            with patch.object(rvc_cpu_fixture_check,'active_games',return_value=[dict(name='Fortnite',pid=1)]), \
                 patch.object(rvc_cpu_fixture_check,'RvcProcessStream') as worker:
                self.assertEqual(rvc_cpu_fixture_check.main(args),2)
                worker.assert_not_called()
            self.assertFalse(json.loads(report.read_text())['worker_started'])


if __name__=='__main__':
    unittest.main()
