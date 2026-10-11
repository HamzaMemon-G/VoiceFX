"""Offline character controls; no models or microphone required."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "app"))
import numpy as np
from character import Character

rng = np.random.default_rng(7)
x = rng.normal(0, 0.03, 32000).astype(np.float32)
assert np.array_equal(Character().process(x)[1024:], x[:-1024])
a = Character().process(x, -5, -3)
c = Character()
b = np.concatenate([c.process(x[i : i + 317], -5, -3) for i in range(0, len(x), 317)])
assert np.array_equal(a, b)
assert np.count_nonzero(Character().process(np.zeros(16000), -5, -3)) == 0
tone = (0.1 * np.sin(2 * np.pi * 240 * np.arange(32000) / 16000)).astype(np.float32)
for resonance in (-3, 0, 3):
    y = Character().process(tone, -5, resonance)
    peak = np.argmax(abs(np.fft.rfft(y[8000:24000] * np.hanning(16000))))
    assert abs(peak - 240 * 2 ** (-5 / 12)) < 3
    assert np.isfinite(y).all() and abs(y).max() < 0.5
print(
    "PASS: exact neutral delay, silence, block continuity, pitch independent of resonance, bounded startup"
)
