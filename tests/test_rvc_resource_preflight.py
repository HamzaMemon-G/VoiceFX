"""A running game must block diagnostic model loading, not close the game."""
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
from threading import Event

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'app'))
import rvc_cpu_check
import rvc_cpu_fixture_check
from windows_resource_guard import GameLoadWatch


class ResourcePreflight(unittest.TestCase):
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
