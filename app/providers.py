import ctypes
import numpy as np
from paths import RESOURCES


class Native:
    def __init__(self, a):
        self.a = a
        self.frames = 960
        self.ms = 20
        self.lib = ctypes.CDLL(str(RESOURCES / "native/voicefx.dll"))
        self.lib.fx_create.argtypes = [ctypes.c_int]
        self.lib.fx_create.restype = ctypes.c_void_p
        self.lib.fx_destroy.argtypes = [ctypes.c_void_p]
        self.lib.fx_process.argtypes = [
            ctypes.c_void_p,
            ctypes.POINTER(ctypes.c_float),
            ctypes.POINTER(ctypes.c_float),
            ctypes.c_int,
        ] + [ctypes.c_int] * 6
        self.ptr = self.lib.fx_create(
            {"clean": 0, "deep": 1, "police": 2, "atc": 2, "robot": 3}[a.model_name]
        )
        if not self.ptr:
            raise RuntimeError("Cannot prepare native effect")

    def reset(self):
        self.lib.fx_destroy(self.ptr)
        self.ptr = self.lib.fx_create(
            {"clean": 0, "deep": 1, "police": 2, "atc": 2, "robot": 3}[
                self.a.model_name
            ]
        )

    def convert48(self, x, pitch=0, formant=0):
        x = np.ascontiguousarray(x, dtype=np.float32)
        y = np.empty_like(x)
        s = dict(self.a.effect)
        s["style"] = int(self.a.model_name == "atc")
        self.lib.fx_process(
            self.ptr,
            x.ctypes.data_as(ctypes.POINTER(ctypes.c_float)),
            y.ctypes.data_as(ctypes.POINTER(ctypes.c_float)),
            len(x),
            *[
                int(s[k])
                for k in ("pitch", "style", "drive", "noise", "squelch", "clarity")
            ],
        )
        return y

    def __del__(self):
        if getattr(self, "ptr", None):
            self.lib.fx_destroy(self.ptr)


def make_provider(a):
    if a.model_name not in ("original", "hfg"):
        return Native(a)
    from engine import Converter

    model = Converter(2, a.factor, a.model_name)
    import time

    samples = []
    x = np.zeros(model.frames, dtype=np.float32)
    for i in range(32):
        t = time.perf_counter()
        model.convert48(x, a.pitch, a.formant)
        if i >= 8:
            samples.append((time.perf_counter() - t) * 1000)
    if np.percentile(samples, 95) > model.ms * 0.8:
        raise RuntimeError(
            "AI cannot sustain this buffer. Choose Stable or a native effect."
        )
    return model
