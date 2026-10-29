"""Optional, worker-process-only adapter for the locally approved RVC runtime.

No devices, routing or application selections are opened or changed here. The
external RVC checkout and its dependencies are still required. This adapter is
not enabled by the app and does not certify real-time or laptop performance.
"""

import hashlib
import importlib.util
import json
import math
import os
from pathlib import Path
import sys
from concurrent.futures import ThreadPoolExecutor
from threading import Lock
from types import SimpleNamespace
import time

import numpy as np


class FrozenRvcCpu:
    sample_rate = 48000
    frames = 9600
    ms = 200

    def __init__(self, snapshot, rvc_root, ort_packages):
        if "torch" in sys.modules:
            raise RuntimeError("Load this backend in a dedicated worker process")
        snapshot, rvc_root = Path(snapshot).resolve(), Path(rvc_root).resolve()
        manifest = json.loads((snapshot / "provenance.json").read_text())
        required = ["models/pop-pitch-refined.pth", "runtime/features.pt",
                    "runtime/synth.onnx", "runtime/rmvpe32.onnx", "settings.json",
                    "reproduction/rvc_worker.py", "reproduction/rtrvc.py"]
        for name in required:
            expected = manifest["sha256"].get(name)
            digest = hashlib.sha256((snapshot / name).read_bytes()).hexdigest()
            if not expected or digest != expected:
                raise RuntimeError(f"Approved runtime checksum mismatch: {name}")
        # The external inference implementation must match the preserved one.
        if hashlib.sha256((rvc_root / "infer/rtrvc.py").read_bytes()).hexdigest() != manifest["sha256"]["reproduction/rtrvc.py"]:
            raise RuntimeError("External RVC inference implementation has changed")
        settings = json.loads((snapshot / "settings.json").read_text())
        fixed = dict(block_ms=200, extra_ms=500, crossfade_ms=40,
                     sample_rate=48000, feature_threads=4, pitch_threads=2,
                     synth_threads=6, parallel_features_pitch=True, spinning=False)
        if any(settings.get(key) != value for key, value in fixed.items()):
            raise RuntimeError("Approved runtime settings have changed")

        os.environ.update(CUDA_VISIBLE_DEVICES="-1", OMP_NUM_THREADS="4",
                          MKL_NUM_THREADS="4", OMP_WAIT_POLICY="PASSIVE",
                          RVC_CUDA_GRAPH="0", TORCH_FORCE_NO_WEIGHTS_ONLY_LOAD="1")
        sys.path[:0] = [str(Path(ort_packages).resolve()), str(rvc_root)]
        import torch
        import onnxruntime as ort
        self.torch = torch
        torch.set_num_threads(4)
        torch.set_num_interop_threads(1)
        spec = importlib.util.spec_from_file_location("voicefx_frozen_rvc_engine",
                    snapshot / "reproduction/rvc_worker.py")
        module = importlib.util.module_from_spec(spec)
        # Upstream Config parses process arguments during construction. Its
        # launcher options must not consume this service's bundle arguments.
        service_argv = sys.argv
        try:
            sys.argv = [service_argv[0]]
            spec.loader.exec_module(module)
            engine = module.RVCStreamEngine(dict(rvc_root=str(rvc_root),
                        model_path=str(snapshot / "models/pop-pitch-refined.pth"),
                        index_path="", sample_rate=48000, block_ms=200,
                        crossfade_ms=40, extra_ms=500))
        finally:
            sys.argv = service_argv
        if str(engine.config.device) != "cpu":
            raise RuntimeError("CPU worker selected an unexpected device")
        excitation, upp = engine.rvc.net_g.dec.m_source, engine.rvc.net_g.dec.upp
        head, length = engine.skip_head, engine.return_length
        engine.prewarm()  # Initialize the fixed native pitch wrapper/mel frontend.

        def session(path, threads):
            options = ort.SessionOptions()
            options.intra_op_num_threads = threads
            options.inter_op_num_threads = 1
            options.graph_optimization_level = ort.GraphOptimizationLevel.ORT_ENABLE_ALL
            for key in ("session.intra_op.allow_spinning", "session.inter_op.allow_spinning"):
                options.add_session_config_entry(key, "0")
            return ort.InferenceSession(str(path), sess_options=options,
                                       providers=["CPUExecutionProvider"])

        class Features(torch.nn.Module):
            def __init__(self):
                super().__init__()
                self.compiled = torch.jit.load(str(snapshot / "runtime/features.pt")).eval()

            def forward(self, input_values, **kwargs):
                return SimpleNamespace(last_hidden_state=self.compiled(input_values))

        pitch_session = session(snapshot / "runtime/rmvpe32.onnx", 2)

        class Pitch(torch.nn.Module):
            def forward(self, mel):
                if tuple(mel.shape) != (1, 128, 32):
                    raise RuntimeError("Unexpected pitch input shape")
                return torch.from_numpy(pitch_session.run(None, {"mel": mel.numpy()})[0])

        class Synth(torch.nn.Module):
            def __init__(self):
                super().__init__()
                self.source = excitation
                self.session = session(snapshot / "runtime/synth.onnx", 6)
                self.noise_shape = next(x.shape for x in self.session.get_inputs() if x.name == "noise")

            def infer(self, phone, lengths, pitch, pitchf, speaker, *static):
                if tuple(map(int, static)) != (head, length, length):
                    raise RuntimeError("Unexpected synthesis context")
                noise = torch.randn(self.noise_shape)
                harmonic = self.source(pitchf[:, head:head + length], upp)[0]
                feed = dict(phone=phone.numpy(), lengths=lengths.numpy(),
                            pitch=pitch.numpy(), speaker=speaker.numpy(),
                            noise=noise.numpy(), harmonic_source=harmonic.numpy())
                return (torch.from_numpy(self.session.run(None, feed)[0]),)

        engine.rvc.model = Features().eval()
        engine.rvc.model_rmvpe.model = Pitch().eval()
        engine.rvc.net_g = Synth().eval()
        self._pool = ThreadPoolExecutor(max_workers=1, thread_name_prefix="voicefx-pitch")
        self._future = None
        self._lock = Lock()
        self._closed = False
        native_infer, native_f0 = engine.rvc.infer, engine.rvc.get_f0

        def pitch_job(audio, key, method):
            with torch.inference_mode():
                return native_f0(audio, key, method)

        def get_f0(*args, **kwargs):
            return self._future.result() if self._future is not None else native_f0(*args, **kwargs)

        def infer(audio, block_frames, skip_head, return_length, method):
            if method != "rmvpe":
                raise RuntimeError("Approved runtime requires RMVPE")
            count = 5120 * ((block_frames + 799) // 5120 + 1) - 160
            self._future = self._pool.submit(pitch_job, audio[-count:],
                         engine.rvc.f0_up_key - engine.rvc.formant_shift, method)
            try:
                return native_infer(audio, block_frames, skip_head, return_length, method)
            finally:
                try:
                    self._future.result()
                finally:
                    self._future = None

        engine.rvc.get_f0, engine.rvc.infer = get_f0, infer
        self.engine = engine
        self.last_compute_ms = None

    def warmup(self):
        with self._lock:
            if self._closed:
                raise RuntimeError("Worker is closed")
            for _ in range(3):
                self.engine.prewarm()
            self.torch.manual_seed(1234)

    def convert48(self, audio, pitch=-9):
        audio = np.asarray(audio, dtype=np.float32)
        if audio.shape != (self.frames,) or not np.isfinite(audio).all():
            raise ValueError("Expected one finite mono 200ms audio packet")
        if not math.isfinite(pitch) or not -24 <= pitch <= 24:
            raise ValueError("Invalid pitch")
        with self._lock:
            if self._closed:
                raise RuntimeError("Worker is closed")
            start = time.perf_counter()
            with self.torch.inference_mode():
                result = self.engine.process(audio, float(pitch), 0., 0., 1., -60., 0)
            self.last_compute_ms = 1000 * (time.perf_counter() - start)
            if result.shape != audio.shape or not np.isfinite(result).all():
                raise RuntimeError("Invalid CPU conversion output")
            return result.copy()

    def close(self):
        with self._lock:
            if not self._closed:
                self._closed = True
                self._pool.shutdown(wait=True, cancel_futures=True)

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()
