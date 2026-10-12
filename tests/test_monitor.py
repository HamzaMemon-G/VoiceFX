"""Self-monitoring switches immediately without changing the destination."""
import sys
from pathlib import Path
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "app"))
from monitor import Monitor

monitor = Monitor(True)
destination = np.full((8, 2), 0.25, dtype=np.float32)
monitor.submit(destination[:, 0])
headphones = np.zeros_like(destination)
monitor.callback(headphones, 8, None, None)
assert np.all(headphones == 0.25)
monitor.submit(destination[:, 0])
monitor.enabled = False
monitor.callback(headphones, 8, None, None)
assert not headphones.any()
assert np.all(destination == 0.25)
monitor.enabled = True
monitor.callback(headphones, 8, None, None)
assert not headphones.any(), "Re-enabling must not replay stale audio"
for _ in range(100):
    monitor.submit(destination[:, 0])
assert monitor.packets.qsize() == 2
print("PASS: headphone toggle, independent destination and bounded buffering")
