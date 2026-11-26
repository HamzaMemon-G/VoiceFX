"""Optional headphone playback, isolated from the voice destination."""

import queue


class Monitor:
    def __init__(self, enabled=False):
        self.enabled = enabled
        self.packets = queue.Queue(maxsize=2)

    def submit(self, samples):
        if not self.enabled:
            return
        try:
            self.packets.put_nowait(samples.copy())
        except queue.Full:
            pass  # Headphone delays must never stall the voice destination.

    def callback(self, outdata, frames, timing, status):
        outdata.fill(0)
        latest = None
        while True:
            try:
                latest = self.packets.get_nowait()
            except queue.Empty:
                break
        if self.enabled and latest is not None and len(latest) == frames:
            outdata[:] = latest[:, None]
