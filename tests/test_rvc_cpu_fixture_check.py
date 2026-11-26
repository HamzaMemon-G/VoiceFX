"""Fixture-provided filenames must stay inside the selected directory."""
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'app'))
from rvc_cpu_fixture_check import checked_path


class FixturePaths(unittest.TestCase):
    def test_fixture_path_stays_inside_root(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder)
            self.assertEqual(checked_path(root,'public.wav'),root.resolve()/'public.wav')
            with self.assertRaises(ValueError):
                checked_path(root,'../outside.wav')
            with self.assertRaises(ValueError):
                checked_path(root,str(root.parent/'outside.wav'))


if __name__=='__main__':
    unittest.main()
