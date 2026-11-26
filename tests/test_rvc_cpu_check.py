"""A completed file replay must not conceal dropouts or inadequate CPU headroom."""
from pathlib import Path
import sys
import unittest

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'app'))
from rvc_cpu_check import evaluate


class CheckCriteria(unittest.TestCase):
    def test_dropouts_or_no_playback_cannot_pass(self):
        self.assertFalse(evaluate(True,.5,None,960,[100.],[.2])['simulated_cpu_gate_passed'])
        self.assertFalse(evaluate(True,None,None,0,[100.],[.2])['simulated_cpu_gate_passed'])
        self.assertFalse(evaluate(False,.5,'worker stopped',0,[100.],[.2])['simulated_cpu_gate_passed'])

    def test_uninterrupted_playback_alone_does_not_prove_headroom(self):
        result=evaluate(True,.5,None,0,[180.]*100,[.2])
        self.assertTrue(result['uninterrupted_simulation'])
        self.assertFalse(result['simulated_cpu_gate_passed'])

    def test_callback_overrun_cannot_pass_model_headroom(self):
        self.assertFalse(evaluate(True,.5,None,0,[100.],[21.])['simulated_cpu_gate_passed'])
        self.assertTrue(evaluate(True,.5,None,0,[100.],[.2])['simulated_cpu_gate_passed'])


if __name__=='__main__':
    unittest.main()
