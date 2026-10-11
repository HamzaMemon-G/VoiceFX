"""Synthetic driver: mute and device loss. Never opens real audio devices."""

import sys
import threading
import time
import tempfile
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "app"))
import numpy as np
import audio
import providers


class Provider:
    frames = 960
    ms = 20

    def reset(self):
        pass

    def convert48(self, x, *args):
        return x * 0.5


class CallbackStop(Exception):
    pass


class Driver:
    def __init__(self, **kwargs):
        self.callback = kwargs["callback"]
        self.stopped = threading.Event()
        self.output = []
        self.loss = False

    def __enter__(self):
        def run():
            while not self.stopped.is_set():
                out = np.ones((960, 2), dtype=np.float32)
                try:
                    self.callback(
                        np.full((960, 2), 0.3, dtype=np.float32),
                        out,
                        960,
                        None,
                        SimpleNamespace(
                            input_overflow=self.loss, output_underflow=False
                        ),
                    )
                except CallbackStop:
                    break
                self.output.append(out.copy())
                time.sleep(0.05)

        self.thread = threading.Thread(target=run)
        self.thread.start()
        return self

    def __exit__(self, *args):
        self.stopped.set()
        self.thread.join(2)


drivers = []


def stream(**kwargs):
    d = Driver(**kwargs)
    drivers.append(d)
    return d


sd = SimpleNamespace(
    Stream=stream,
    CallbackStop=CallbackStop,
    query_hostapis=lambda i: {"name": "MME"},
    query_devices=lambda: [
        {
            "name": "Test input",
            "max_input_channels": 2,
            "max_output_channels": 0,
            "hostapi": 0,
        },
        {
            "name": "Test output",
            "max_input_channels": 0,
            "max_output_channels": 2,
            "hostapi": 0,
        },
    ],
)
with (
    tempfile.TemporaryDirectory() as tmp,
    patch.dict(sys.modules, {"sounddevice": sd}),
    patch.object(providers, "make_provider", lambda a: Provider()),
    patch.object(audio, "DATA", Path(tmp)),
):
    messages = []
    a = audio.Audio("Test input", "Test output", messages.append, "clean")
    a.volume = 1
    worker = threading.Thread(target=a.run)
    worker.start()
    assert a.ready.wait(3)
    time.sleep(0.5)
    assert not a.error and any(np.max(y) > 0 for y in drivers[-1].output)
    # Only processed samples reach playback; no accidental dry mix.
    assert all(np.max(y) <= 0.151 for y in drivers[-1].output)
    a.mute = True
    time.sleep(0.3)
    assert all(np.count_nonzero(y) == 0 for y in drivers[-1].output[-3:])
    drivers[-1].loss = True
    worker.join(3)
    assert not worker.is_alive() and "driver missed" in a.error
    assert np.count_nonzero(drivers[-1].output[-1]) == 0
print("PASS: processed-only playback, exact mute, device failure stops silently")
