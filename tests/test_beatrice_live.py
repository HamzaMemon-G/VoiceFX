"""Offline integration check for a locally installed official Beatrice VST3."""

import sys
import time
import wave
from pathlib import Path

import numpy as np
from scipy.signal import resample_poly

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "app"))
from beatrice_vst import Beatrice, installed_models


def run(source_path):
    if not installed_models():
        raise RuntimeError("Set VOICEFX_BEATRICE_VST to the official local VST3 first")
    with wave.open(str(source_path), "rb") as wav:
        if wav.getsampwidth() != 2:
            raise ValueError("Test source must be 16-bit PCM")
        rate = wav.getframerate()
        source = np.frombuffer(wav.readframes(wav.getnframes()), dtype="<i2").astype(np.float32) / 32768
        source = source.reshape(-1, wav.getnchannels()).mean(axis=1)
    if rate != 48000:
        source = resample_poly(source, 48000, rate).astype("float32")
    for key in ("pop-smoke", "opie"):
        for frames in (2400, 4800):
            padded = np.pad(source, (0, -len(source) % frames))
            model = Beatrice(key)
            model.frames, model.ms = frames, frames // 48
            blocks = []
            times = []
            for offset in range(0, len(padded), frames):
                start = time.perf_counter()
                blocks.append(model.convert48(padded[offset:offset + frames], -5, -1))
                times.append((time.perf_counter() - start) * 1000)
            streamed = np.concatenate(blocks)
            batch_model = Beatrice(key)
            batch_model.plugin.pitch_shift_st = -5.0
            batch_model.plugin.formant_shift_st = -1.0
            batch = np.asarray(batch_model.plugin.process(padded[None, :], sample_rate=48000, buffer_size=frames, reset=False)).reshape(-1)
            error = float(np.max(np.abs(streamed - batch)))
            p95 = float(np.percentile(times[5:], 95))
            print(key, model.ms, "ms p95", round(p95, 2), "max_error", error, "output_rms", round(float(np.sqrt(np.mean(streamed ** 2))), 5))
            assert error < 1e-5, "Block and batch conversions differ"
            assert np.isfinite(streamed).all() and np.sqrt(np.mean(streamed ** 2)) > 0.001
            assert p95 < model.ms * 0.8, "Desktop cannot sustain real-time processing"


if __name__ == "__main__":
    run(Path(sys.argv[1]))
