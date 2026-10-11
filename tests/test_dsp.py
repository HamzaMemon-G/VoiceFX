"""Offline native effect invariants; no audio device is opened."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "app"))
import numpy as np
from providers import Native
from types import SimpleNamespace


def provider(mode):
    return Native(
        SimpleNamespace(
            model_name=mode,
            effect=dict(pitch=9, style=0, drive=70, noise=0, squelch=-65, clarity=35),
        )
    )


x = (0.15 * np.sin(2 * np.pi * 220 * np.arange(48000) / 48000)).astype(np.float32)
assert np.array_equal(provider("clean").convert48(x), x)
results = {}
for mode in ("deep", "police", "atc", "robot"):
    a = provider(mode)
    y = a.convert48(x)
    assert np.isfinite(y).all() and abs(y).max() <= 1
    b = provider(mode)
    z = np.concatenate([b.convert48(x[i : i + 317]) for i in range(0, len(x), 317)])
    assert np.array_equal(y, z), mode + " depends on block boundaries"
    assert (
        np.count_nonzero(provider(mode).convert48(np.zeros(960, dtype=np.float32))) == 0
    )
    results[mode] = y
assert not np.allclose(results["police"], results["atc"])
robot = provider("robot")
robot.a.effect["noise"] = 100
assert np.array_equal(robot.convert48(x), x)
print(
    "PASS: clean identity, silent idle, finite bounded output, chunk continuity, distinct radio styles, robot blend"
)
