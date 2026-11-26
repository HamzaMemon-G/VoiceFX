"""Device-free callback adapter for an explicitly selected experimental session."""
import math
import numpy as np


class RvcHostCallback:
    def __init__(self, session, stop, callback_stop):
        self.session = session
        self.stop = stop
        self.callback_stop = callback_stop
        self.mute = False
        self.volume = 1.0
        self.error = ""

    def __call__(self, indata, outdata, frames, timing, status):
        outdata.fill(0)
        if self.stop.is_set() or self.error:
            raise self.callback_stop
        if status.input_overflow or status.output_underflow:
            self.error = "Audio driver missed a deadline. Audio stopped."
            self.stop.set()
            return
        if not math.isfinite(self.volume) or not 0 <= self.volume <= 1:
            self.error = "Invalid playback volume."
            self.stop.set()
            return
        try:
            self._render(indata, outdata, frames)
        except Exception as exc:
            outdata.fill(0)
            self.error = "Voice callback failed: " + type(exc).__name__
            self.stop.set()

    def _render(self, indata, outdata, frames):
        state = self.session.status()
        if state['state'] in ('fault', 'stopped'):
            self.error = "Voice worker stopped: " + str(state.get('fault') or 'No microphone fallback')
            self.stop.set()
            return
        if (indata.ndim != 2 or len(indata) != frames or
                outdata.ndim != 2 or len(outdata) != frames or
                indata.shape[1] < 1 or outdata.shape[1] < 1):
            self.error = "Unexpected audio callback shape."
            self.stop.set()
            return
        output = self.session.process(indata.mean(axis=1), mute=self.mute, volume=self.volume)
        if output.shape != (frames,) or not np.isfinite(output).all():
            raise ValueError("Invalid converted callback output")
        if not self.stop.is_set():
            outdata[:] = output[:, None]
