"""Exercise the real native ABI without opening audio devices."""
import ctypes
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
import numpy as np
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'app'))
from providers import Native

class NativeBoundaryTests(unittest.TestCase):
    def make(self):
        return Native(SimpleNamespace(model_name='deep', effect=dict(pitch=9,style=0,drive=70,noise=0,squelch=-65,clarity=35)))

    def test_invalid_audio_is_rejected_before_poisoning_filter(self):
        effect=self.make()
        for invalid in (np.zeros((4,2)),np.array([np.nan]),np.array([np.inf]),np.array([1j]),np.array(1.0)):
            with self.assertRaises(ValueError):effect.convert48(invalid)
        np.testing.assert_array_equal(effect.convert48(np.zeros(960)),np.zeros(960))

    def test_reset_allocation_failure_leaves_no_dangling_handle(self):
        effect=self.make()
        with patch.object(effect.lib,'fx_create',return_value=None):
            with self.assertRaises(RuntimeError):effect.reset()
        self.assertIsNone(effect.ptr)
        with self.assertRaises(RuntimeError):effect.convert48(np.zeros(960))

    def test_native_invalid_mode_and_null_handle(self):
        effect=self.make()
        self.assertFalse(effect.lib.fx_create(-1))
        self.assertFalse(effect.lib.fx_create(4))
        audio=np.ones(960,dtype=np.float32);out=np.ones_like(audio)
        ptr=ctypes.POINTER(ctypes.c_float)
        effect.lib.fx_process(None,audio.ctypes.data_as(ptr),out.ctypes.data_as(ptr),960,9,0,70,0,-65,35)
        np.testing.assert_array_equal(out,np.zeros_like(out))

    def test_extreme_settings_stay_finite_and_bounded(self):
        effect=self.make()
        effect.a.effect.update(pitch=-2147483648,drive=2147483647,noise=-999,clarity=999,squelch=-999)
        result=effect.convert48(np.ones(48000,dtype=np.float32))
        self.assertTrue(np.isfinite(result).all())
        self.assertLessEqual(float(np.max(np.abs(result))),1.)

if __name__=='__main__':unittest.main()
