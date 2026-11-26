"""The optional execution-speed request changes only its own child process."""
import json
import os
from pathlib import Path
import subprocess
import sys
import unittest

APP=Path(__file__).resolve().parents[1]/'app'
sys.path.insert(0,str(APP))


@unittest.skipUnless(os.name=='nt','Windows-only process-local hint')
class ProcessLocalHint(unittest.TestCase):
    def test_readback_in_child_and_parent_state_unchanged(self):
        from windows_worker_qos import execution_speed_state
        before=execution_speed_state()
        code='import sys,json; sys.path.insert(0,sys.argv[1]); from windows_worker_qos import execution_speed_state; print(json.dumps(execution_speed_state(True)))'
        child=json.loads(subprocess.check_output([sys.executable,'-c',code,str(APP)],text=True,
                         creationflags=subprocess.CREATE_NO_WINDOW))
        self.assertTrue(child['requested'] and child['applied'])
        self.assertEqual(child['control_mask']&1,1)
        self.assertEqual(child['state_mask']&1,0)
        self.assertNotEqual(child['pid'],os.getpid())
        after=execution_speed_state()
        self.assertEqual((before['control_mask'],before['state_mask']),
                         (after['control_mask'],after['state_mask']))


if __name__=='__main__':
    unittest.main()
