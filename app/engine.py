"""Local LLVC streaming adapter. No cloud, GPU, or dry-audio fallback."""

import hashlib
import json
import sys
import time
from pathlib import Path
import numpy as np
import torch
from scipy.signal import butter, sosfilt

ROOT = Path(__file__).resolve().parent
from paths import RESOURCES

MODELS = {
    "original": (
        "llvc.pth",
        "llvc",
        "cceb7ab9621f84d62d283725ae3281cacb04f762d6a088fe3e97c1a29d4b8c0e",
    ),
    "hfg": (
        "llvc-hfg.pth",
        "llvc_hfg",
        "ca046f9a77b36ebfe473923503c5a69260af67f8a1dac317483f2e00ae28e4ed",
    ),
}
sys.path.insert(0, str(RESOURCES / "vendor" / "LLVC"))
from model import Net
from character import Character


class Converter:
    def __init__(self, threads=2, factor=4, model_name="original"):
        torch.set_num_threads(threads)
        filename, experiment, checksum = MODELS[model_name]
        config = json.loads(
            (
                RESOURCES / "vendor/LLVC/experiments" / experiment / "config.json"
            ).read_text()
        )
        self.model = Net(**config["model_params"]).eval()
        from paths import DATA

        path = DATA / "models" / filename
        if not path.exists():
            raise RuntimeError("AI models are missing. Click Get AI models first.")
        if hashlib.sha256(path.read_bytes()).hexdigest() != checksum:
            raise RuntimeError("AI model checksum mismatch")
        checkpoint = torch.load(path, map_location="cpu", weights_only=True)
        self.model.load_state_dict(checkpoint["model"], strict=True)
        self.size = self.model.L * self.model.dec_chunk_size * factor
        self.frames = self.size * 3
        self.ms = self.size / 16
        self.reset()

    def reset(self):
        self.buffers = self.model.init_buffers(1, torch.device("cpu"))
        self.ctx = self.model.convnet_pre.init_ctx_buf(1, torch.device("cpu"))
        self.front = torch.zeros(2 * self.model.L)
        self.filter = butter(8, 7000, fs=48000, output="sos")
        self.down_state = np.zeros((len(self.filter), 2))
        self.up_state = self.down_state.copy()
        self.character = Character()

    def convert16(self, x):
        x = torch.as_tensor(x, dtype=torch.float32)
        if len(x) != self.size:
            raise ValueError("Wrong AI chunk size")
        # Causal live adaptation of upstream infer_stream: two L of history;
        # no future read. Adds L samples of alignment delay vs offline shifting.
        chunk = torch.cat((self.front, x))
        self.front = x[-2 * self.model.L :].clone()
        with torch.inference_mode():
            y, *state = self.model(
                chunk[None, None], *self.buffers, self.ctx, pad=not self.model.lookahead
            )
        self.buffers = tuple(state[:3])
        self.ctx = state[3]
        y = y.flatten().numpy().copy()
        if len(y) != self.size or not np.isfinite(y).all():
            raise RuntimeError("Invalid AI output; audio stopped")
        return y

    def convert48(self, x, pitch=0, formant=0):
        filtered, self.down_state = sosfilt(self.filter, x, zi=self.down_state)
        y = self.convert16(filtered[::3].astype(np.float32))
        y = self.character.process(y, pitch, formant)
        up = np.zeros(self.frames)
        up[::3] = y * 3
        up, self.up_state = sosfilt(self.filter, up, zi=self.up_state)
        return np.clip(up, -0.95, 0.95).astype(np.float32)


def benchmark(threads, factor, count=160, model_name="original"):
    start = time.perf_counter()
    c = Converter(threads, factor, model_name)
    load = time.perf_counter() - start
    x = (0.08 * np.sin(2 * np.pi * 170 * np.arange(c.frames) / 48000)).astype(
        np.float32
    )
    for _ in range(12):
        c.convert48(x)
    times = []
    for _ in range(count):
        t = time.perf_counter()
        c.convert48(x)
        times.append((time.perf_counter() - t) * 1000)
    return dict(
        model=model_name,
        threads=threads,
        factor=factor,
        chunk_ms=c.ms,
        load_seconds=load,
        mean_ms=float(np.mean(times)),
        p95_ms=float(np.percentile(times, 95)),
        max_ms=max(times),
        headroom_pass=bool(np.percentile(times, 95) < c.ms * 0.7),
    )


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("--model", choices=MODELS, default="original")
    parser.add_argument("--quick", action="store_true")
    args = parser.parse_args()
    results = []
    for threads in (2,) if args.quick else (1, 2, 4):
        for factor in (4, 8) if args.quick else (2, 4, 8):
            result = benchmark(threads, factor, model_name=args.model)
            results.append(result)
            print(json.dumps(result), flush=True)
    filename = "benchmark.json" if args.model == "original" else "benchmark-hfg.json"
    from paths import DATA

    (DATA / filename).write_text(json.dumps(results, indent=2))
