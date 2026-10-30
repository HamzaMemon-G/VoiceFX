"""Optional bounded local process transport; not enabled by the audio app."""

import base64
from collections import deque
import json
import math
from pathlib import Path
from queue import Empty, Full, Queue
import subprocess
import time
from threading import Event, Lock, Thread

import numpy as np

from stream_buffer import PacketAudioBuffer

SERVICE_PATH = Path(__file__).with_name("rvc_cpu_service.py")


class RvcProcessStream:
    """Keep model loading, inference and pipe I/O off the caller's callback.

    Callers must wait for ``status()['ready']`` before submitting capture audio.
    Faults stop playback with silence and require constructing a new stream.
    Buffering and timeout choices are explicit; this is not live certification.
    """

    frames = 9600

    def __init__(self, python, snapshot, rvc_root, ort_packages, log_file, *,
                 startup_packets, max_packets, startup_timeout=600,
                 conversion_timeout=5, pitch=-9, dynamic_block_base=0,
                 synthesis_backend="ort", openvino_packages=None):
        if synthesis_backend not in ("ort", "openvino"):
            raise ValueError("Unsupported CPU synthesis backend")
        if synthesis_backend == "openvino" and not openvino_packages:
            raise ValueError("Explicit isolated OpenVINO package path required")
        if type(dynamic_block_base) is not int or dynamic_block_base not in (0, 4):
            raise ValueError("Unsupported experimental scheduling option")
        if not math.isfinite(pitch) or not -24 <= pitch <= 24:
            raise ValueError("Invalid pitch")
        if (not math.isfinite(startup_timeout) or not math.isfinite(conversion_timeout)
                or startup_timeout <= 0 or conversion_timeout <= 0):
            raise ValueError("Timeouts must be positive")
        self.buffer = PacketAudioBuffer(self.frames, 48000,
                    startup_packets=startup_packets, max_packets=max_packets)
        self._inputs = Queue(maxsize=max_packets)
        self._messages = Queue(maxsize=4)
        self._stop = Event()
        self._ready = Event()
        self._submit_lock = Lock()
        self._metrics_lock = Lock()
        self._metrics = deque(maxlen=256)
        self._sequence = 0
        self._process = None
        self._pitch = pitch
        self._dynamic_block_base = dynamic_block_base
        self._synthesis_backend = synthesis_backend
        self._last_compute_ms = None
        command = [str(python), "-u", str(SERVICE_PATH), "--snapshot", str(snapshot),
                   "--rvc-root", str(rvc_root), "--ort-packages", str(ort_packages),
                   "--dynamic-block-base", str(dynamic_block_base),
                   "--synthesis-backend", synthesis_backend]
        if synthesis_backend == "openvino":
            command.extend(["--openvino-packages", str(openvino_packages)])
        self._thread = Thread(target=self._run,
            args=(command, Path(log_file), startup_timeout, conversion_timeout),
            daemon=True, name="voicefx-transport")
        self._thread.start()

    def _fail(self, reason):
        self.buffer.abort(reason)
        self._ready.clear()
        self._stop.set()

    def _receive(self, timeout):
        message = self._messages.get(timeout=timeout)
        if message.get("type") == "error":
            raise RuntimeError(message.get("message", "CPU worker failed"))
        return message

    def _reader(self, pipe):
        try:
            while True:
                line = pipe.readline(65537)
                if not line:
                    raise RuntimeError("CPU worker disconnected")
                if len(line) > 65536 or not line.endswith("\n"):
                    raise RuntimeError("Invalid worker response size")
                message = json.loads(line)
                if not isinstance(message, dict):
                    raise RuntimeError("Invalid worker response")
                self._messages.put_nowait(message)
        except Exception:
            try:
                self._messages.put_nowait(dict(type="error", message="CPU worker protocol disconnected or invalid"))
            except Full:
                self._fail("CPU worker protocol overflow")

    def _run(self, command, log_file, startup_timeout, conversion_timeout):
        process = None
        try:
            log_file.parent.mkdir(parents=True, exist_ok=True)
            with log_file.open("w", encoding="utf8") as log:
                if self._stop.is_set():
                    return
                process = subprocess.Popen(command, stdin=subprocess.PIPE,
                    stdout=subprocess.PIPE, stderr=log, text=True, encoding="utf8",
                    bufsize=1, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
                self._process = process
                reader = Thread(target=self._reader, args=(process.stdout,), daemon=True)
                reader.start()
                message = self._receive(startup_timeout)
                if (message.get("type") != "ready" or message.get("frames") != self.frames
                        or message.get("sample_rate") != 48000
                        or message.get("synthesis_backend", "ort") != self._synthesis_backend
                        or message.get("dynamic_block_base", 0) != self._dynamic_block_base):
                    raise RuntimeError("CPU worker format mismatch")
                if not self._stop.is_set():
                    self._ready.set()
                while not self._stop.is_set():
                    try:
                        sequence, packet, enqueued = self._inputs.get(timeout=.05)
                    except Empty:
                        continue
                    request = dict(type="convert", sequence=sequence, pitch=self._pitch,
                                   audio=base64.b64encode(packet).decode("ascii"))
                    sent = time.perf_counter()
                    process.stdin.write(json.dumps(request) + "\n")
                    process.stdin.flush()
                    message = self._receive(conversion_timeout)
                    if (message.get("type") != "converted"
                            or type(message.get("sequence")) is not int
                            or message["sequence"] != sequence):
                        raise RuntimeError("CPU worker packet mismatch")
                    raw = base64.b64decode(message["audio"], validate=True)
                    if len(raw) != self.frames * 4:
                        raise RuntimeError("CPU worker output size mismatch")
                    compute_ms = message.get("compute_ms")
                    if (type(compute_ms) not in (int, float)
                            or not math.isfinite(compute_ms) or compute_ms < 0):
                        raise RuntimeError("Invalid CPU worker timing")
                    if self._stop.is_set():
                        break
                    self._last_compute_ms = compute_ms
                    received = time.perf_counter()
                    with self._metrics_lock:
                        self._metrics.append(dict(sequence=sequence, compute_ms=compute_ms,
                            input_wait_ms=1000 * (sent - enqueued),
                            roundtrip_ms=1000 * (received - sent)))
                    self.buffer.push(sequence, np.frombuffer(raw, dtype="<f4"))
                if process.poll() is None:
                    process.stdin.write('{"type":"stop"}\n')
                    process.stdin.flush()
                    process.wait(timeout=2)
        except Exception as exc:
            if not self._stop.is_set():
                self._fail(f"CPU transport failed: {type(exc).__name__}")
        finally:
            self._ready.clear()
            if process is not None:
                if process.poll() is None:
                    process.terminate()
                    try:
                        process.wait(timeout=2)
                    except subprocess.TimeoutExpired:
                        process.kill()
                        process.wait(timeout=2)
                for pipe in (process.stdin, process.stdout):
                    if pipe:
                        pipe.close()

    def submit(self, audio):
        """Queue one capture packet without waiting for a model or pipe."""
        with self._submit_lock:
            if not self._ready.is_set() or self._stop.is_set():
                return False
            try:
                packet = np.array(audio, dtype="<f4", copy=True)
                if packet.shape != (self.frames,) or not np.isfinite(packet).all():
                    raise ValueError("Invalid capture packet")
                self._inputs.put_nowait((self._sequence, packet.tobytes(), time.perf_counter()))
                self._sequence += 1
                return True
            except (TypeError, ValueError, OverflowError, Full):
                self._fail("Capture input invalid or worker queue full")
                return False

    def read(self, frames):
        output = self.buffer.read(frames)
        if self.buffer.status()["state"] == "fault":
            self._ready.clear()
            self._stop.set()
        return output

    def status(self):
        return dict(self.buffer.status(), ready=self._ready.is_set(),
                    queued_input_packets=self._inputs.qsize(),
                    worker_pid=self._process.pid if self._process else None,
                    experimental_dynamic_block_base=self._dynamic_block_base,
                    experimental_synthesis_backend=self._synthesis_backend,
                    last_compute_ms=self._last_compute_ms)

    def metrics(self):
        """Last 256 packet timing records; contains no audio or file paths."""
        with self._metrics_lock:
            return list(self._metrics)

    def close(self):
        self._stop.set()
        self._ready.clear()
        self.buffer.abort("Stream closed")
        self._thread.join(timeout=3)
        if self._thread.is_alive() and self._process is not None:
            if self._process.poll() is None:
                self._process.terminate()
            self._thread.join(timeout=3)
        if self._thread.is_alive():
            raise RuntimeError("CPU transport did not stop")

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()
