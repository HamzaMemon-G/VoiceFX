"""Bounded streaming queues. Errors stop output; no microphone fallback."""

import ctypes
import json
import queue
import threading
import time
from contextlib import ExitStack
from monitor import Monitor
from paths import DATA


class Audio:
    def __init__(
        self, input_name, output_name, notify, model_name="original", factor=8,
        monitor_name="",
    ):
        self.pitch = -5.0
        self.formant = -3.0
        self.effect = {
            "pitch": 9,
            "style": 0,
            "drive": 70,
            "noise": 0,
            "squelch": -65,
            "clarity": 35,
        }
        self.model_name = model_name
        self.factor = factor
        self.gain_db = 0
        self.gate_db = -70
        self.input_name = input_name
        self.output_name = output_name
        self.monitor_name = monitor_name
        self.monitor = Monitor()
        self.notify = notify
        self.error = ""
        self.stop = threading.Event()
        self.ready = threading.Event()
        self.mute = False
        self.volume = 0.8
        self.stats = dict(
            blocks=0, misses=0, peak_db=-90, mean_ms=0, max_ms=0, output_peak=0
        )

    def run(self):
        try:
            self._run()
        except Exception as e:
            self.error = str(e)
            self.notify("Audio stopped: " + str(e))

    def _run(self):
        import numpy as np
        import sounddevice as sd
        from providers import make_provider

        kernel = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel.CreateMutexW.restype = ctypes.c_void_p
        kernel.CreateMutexW.argtypes = [
            ctypes.c_void_p,
            ctypes.c_bool,
            ctypes.c_wchar_p,
        ]
        kernel.CloseHandle.argtypes = [ctypes.c_void_p]
        # Prevent Windows from throttling this real-time worker as background work.
        kernel.GetCurrentProcess.restype = ctypes.c_void_p
        process = kernel.GetCurrentProcess()
        kernel.SetPriorityClass.argtypes = [ctypes.c_void_p, ctypes.c_uint]
        kernel.SetPriorityClass(
            process, 0x8000
        )  # above normal, never real-time priority

        class Throttle(ctypes.Structure):
            _fields_ = [
                ("version", ctypes.c_uint),
                ("control", ctypes.c_uint),
                ("state", ctypes.c_uint),
            ]

        throttle = Throttle(1, 1, 0)
        kernel.SetProcessInformation.argtypes = [
            ctypes.c_void_p,
            ctypes.c_int,
            ctypes.c_void_p,
            ctypes.c_uint,
        ]
        kernel.SetProcessInformation(
            process, 4, ctypes.byref(throttle), ctypes.sizeof(throttle)
        )
        lock = kernel.CreateMutexW(None, False, "Local\\VoiceFX.Stream")
        if not lock:
            raise RuntimeError("Cannot acquire audio lock")
        if ctypes.get_last_error() == 183:
            kernel.CloseHandle(lock)
            raise RuntimeError("Another VoiceFX session is running. Stop it first.")
        try:
            self.notify("Preparing voice engine…")
            model = make_provider(self)
            for _ in range(8):
                model.convert48(
                    np.zeros(model.frames, dtype=np.float32), self.pitch, self.formant
                )
            model.reset()

            def resolve(name, direction):
                devices = sd.query_devices()
                found = [
                    i
                    for i, d in enumerate(devices)
                    if d["name"] == name
                    and d["max_" + direction + "_channels"] >= 1
                    and sd.query_hostapis(d["hostapi"])["name"] == "MME"
                ]
                if len(found) != 1:
                    raise RuntimeError(
                        "Select one explicit MME " + direction + " device."
                    )
                index = found[0]
                return index, min(2, devices[index]["max_" + direction + "_channels"])

            inp, in_channels = resolve(self.input_name, "input")
            out, out_channels = resolve(self.output_name, "output")
            incoming = queue.Queue(maxsize=3)
            outgoing = queue.Queue(maxsize=3)
            fault = threading.Event()
            reason = [""]
            started = time.monotonic()
            last = [started]
            sequence = [0]
            pending = [None]
            consecutive = [0]

            def fail(message):
                reason[0] = message
                fault.set()

            # Two chunks provide worker scheduling headroom, without a dry mix.
            # Playback uses fixed sequence deadlines: late results are discarded,
            # so a transient stall cannot permanently increase the voice delay.
            def callback(indata, outdata, frames, timing, status):
                outdata.fill(0)
                self.stats["output_peak"] = 0
                last[0] = time.monotonic()
                if self.stop.is_set() or fault.is_set():
                    raise sd.CallbackStop
                if status.input_overflow or status.output_underflow:
                    fail("Audio driver missed a deadline. Audio stopped.")
                    return
                index = sequence[0]
                sequence[0] += 1
                try:
                    incoming.put_nowait(
                        (index, time.monotonic(), indata.mean(axis=1).copy())
                    )
                except queue.Full:
                    fail("AI input backlog. Audio stopped to prevent growing delay.")
                    return
                expected = index - 2
                if expected < 0:
                    return
                packet = pending[0]
                pending[0] = None
                while True:
                    if packet is None:
                        try:
                            packet = outgoing.get_nowait()
                        except queue.Empty:
                            break
                    if packet[0] < expected:
                        packet = None
                        continue
                    break
                if packet is None or packet[0] > expected:
                    pending[0] = packet
                    self.stats["misses"] += 1
                    consecutive[0] += 1
                    if consecutive[0] >= 3 or (
                        index > 30 and self.stats["misses"] / index > 0.05
                    ):
                        fail("AI repeatedly missed playback deadlines. Audio stopped.")
                    return
                consecutive[0] = 0
                y = packet[1]
                if not self.mute:
                    outdata[:] = y[:, None] * self.volume
                self.stats["output_peak"] = float(np.max(np.abs(outdata)))
                self.monitor.submit(outdata[:, 0])

            count = 0
            total_ms = 0.0
            peak_ms = 0.0
            gate = 0.0
            hold = 0
            import psutil

            process_info = psutil.Process()
            cpu_start = process_info.cpu_times()
            run_start = time.monotonic()
            with ExitStack() as streams:
                if self.monitor_name:
                    try:
                        monitor_device, monitor_channels = resolve(self.monitor_name, "output")
                        if monitor_device == out:
                            raise RuntimeError("Choose headphones separate from the voice destination.")
                        streams.enter_context(sd.OutputStream(
                            device=monitor_device, samplerate=48000,
                            blocksize=model.frames, channels=monitor_channels,
                            dtype="float32", latency=0.12,
                            callback=self.monitor.callback,
                        ))
                    except Exception as e:
                        self.monitor.enabled = False
                        self.notify("Headphone monitoring unavailable: " + str(e))
                streams.enter_context(sd.Stream(
                device=(inp, out),
                samplerate=48000,
                blocksize=model.frames,
                channels=(in_channels, out_channels),
                dtype="float32",
                latency=0.12,
                callback=callback,
                ))
                self.ready.set()
                self.notify(
                    "Running | "
                    + ("Original" if self.model_name == "original" else self.model_name)
                    + " | "
                    + str(model.ms)
                    + " ms chunks"
                )
                while not self.stop.is_set() and not fault.is_set():
                    try:
                        index, stamp, x = incoming.get(timeout=0.2)
                    except queue.Empty:
                        if time.monotonic() - last[0] > 2:
                            fail("Audio device stalled. Audio stopped.")
                        continue
                    if time.monotonic() - stamp > 0.35:
                        fail("AI queue became too old. Audio stopped.")
                        break
                    t = time.perf_counter()
                    y = model.convert48(
                        np.clip(x * 10 ** (self.gain_db / 20), -0.95, 0.95),
                        self.pitch,
                        self.formant,
                    )
                    elapsed = (time.perf_counter() - t) * 1000
                    # A short compute spike may fit within the playback headroom.
                    # Actual playback deadlines, bounded queues and stale-input
                    # checks determine whether the stream can sustain real-time.
                    # Keep idle mic noise from becoming a generated voice; never blend raw mic.
                    rms = float(np.sqrt(np.mean(x * x)))
                    if rms >= 10 ** (self.gate_db / 20):
                        hold = int(0.2 * 48000)
                    else:
                        hold = max(0, hold - model.frames)
                    target = 1.0 if hold else 0.0
                    ramp = min(
                        model.frames, 480
                    )  # 10 ms fade; never an abrupt gate edge
                    y[:ramp] *= np.linspace(gate, target, ramp, dtype=np.float32)
                    y[ramp:] *= target
                    gate = target
                    if index < sequence[0] - 3:
                        continue
                    try:
                        outgoing.put_nowait((index, y))
                    except queue.Full:
                        fail("AI playback stalled. Audio stopped.")
                        break
                    count += 1
                    total_ms += elapsed
                    peak_ms = max(peak_ms, elapsed)
                    self.stats.update(
                        blocks=count,
                        peak_db=round(
                            20 * np.log10(max(float(np.max(np.abs(x))), 1e-9)), 1
                        ),
                        mean_ms=round(total_ms / count, 2),
                        max_ms=round(peak_ms, 2),
                    )
            cpu_end = process_info.cpu_times()
            self.stats["computer_cpu_percent"] = round(
                100
                * (
                    (cpu_end.user + cpu_end.system)
                    - (cpu_start.user + cpu_start.system)
                )
                / max(time.monotonic() - run_start, 0.001)
                / psutil.cpu_count(),
                1,
            )
            self.stats.update(model=self.model_name, chunk_ms=model.ms)
            if fault.is_set():
                self.error = reason[0]
            self.notify(
                reason[0] if fault.is_set() else "Stopped. No microphone audio is sent."
            )
        except Exception as e:
            self.error = str(e)
            self.notify("Audio stopped: " + str(e))
        finally:
            kernel.CloseHandle(lock)
            import psutil

            memory = psutil.Process().memory_info()
            self.stats["peak_working_set_mb"] = round(
                getattr(memory, "peak_wset", memory.rss) / 1048576, 1
            )
            (DATA / "last-session.json").write_text(
                json.dumps(dict(stats=self.stats, error=self.error), indent=2)
            )


def devices():
    import sounddevice as sd

    result = [[], []]
    for d in sd.query_devices():
        if sd.query_hostapis(d["hostapi"])["name"] != "MME":
            continue
        for i, direction in enumerate(("input", "output")):
            if d["max_" + direction + "_channels"] >= 1:
                result[i].append(d["name"])
    return result
