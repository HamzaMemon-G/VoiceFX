# Optional CPU worker integration — in progress

The isolated `app/rvc_cpu_worker.py` adapter loads the preserved, user-approved
200 ms Pop Smoke sound runtime. It must run in a dedicated process because Torch
thread settings and CPU backend environment variables are process-wide. It opens
no audio devices and is not selected or enabled by the application.

The local snapshot, external RVC checkout and isolated ONNX Runtime installation
are required. The snapshot is private and is not included in this repository.
User recordings and conversions must never be uploaded or used for training.

`FrozenRvcCpu(snapshot, rvc_root, ort_packages)` verifies the required files and
the external inference implementation, loads CPU-only sessions, and provides:

- `warmup()`: warm the backend, clear streaming history and reseed the diagnostic
  random stream after warming;
- `convert48(packet, pitch=-9)`: convert exactly 9,600 mono samples at 48 kHz;
- `close()`: stop the pitch executor. The context manager closes it on exit.

Conversion belongs on the worker, never inside an audio device callback. The
separate `PacketAudioBuffer` preserves sample order across callback boundaries
and bounds queued audio. Startup buffering is explicit. Once playback starts,
underflow, overflow, missing packets or invalid model output latch silence and
require a fresh stream. There is no dry microphone fallback or silent replay of
late packets.

`app/rvc_process.py` now provides the separate-process transport. It starts
`rvc_cpu_service.py` with an explicitly supplied Python runtime and bundle paths.
Model startup, conversion and pipe reads/writes happen away from the caller.
`submit()` and `read()` use bounded in-memory queues; capture submissions are
rejected until the worker is ready. Bad packet order, invalid output, queue
overflow and protocol deadlines stop output with silence. `close()` shuts down
only its own worker, including when that worker stalls during startup.

The transport requires explicit startup buffering and queue capacity. These are
not hidden latency allowances. The app still needs opt-in host wiring and
sustained callback/performance validation before this backend can be enabled.

## Evidence and limits

The approved **200 ms block size is not end-to-end latency**. Capture buffering,
inference, model alignment, startup buffering and audio hardware contribute
separately. `PacketAudioBuffer.status()` reports queue audio duration only.

Earlier sustained desktop CPU tests still missed deadlines under competing CPU
activity. Sound approval and an offline waveform comparison do not certify
reliable live performance. No laptop or gaming readiness is claimed, and device,
Voicemeeter, VBAN, game-output and self-monitoring settings remain unchanged.

Lightweight contract tests:

```text
python tests/test_stream_buffer.py
python tests/test_rvc_worker_validation.py
python tests/test_rvc_process.py
```

The local workspace's `work/validate_frozen_app_worker.py` additionally loads the
real preserved runtime and checks public-audio parity, callback-boundary sample
retention and fail-closed behavior. Its report is outside the repository.
`work/validate_app_process_stream.py` additionally checks the real pipe transport
against public and private held-out waveforms. Private artifacts stay local.

`RvcProcessStream.metrics()` keeps at most 256 packet timing records, containing
sequence numbers, input wait, model computation and pipe roundtrip duration.
These diagnostics contain no audio or input paths. They distinguish conversion
cost from transport overhead; they do not measure physical end-to-end latency.

An explicit experimental `dynamic_block_base=4` option applies ONNX Runtime's
dynamic work scheduling to pitch and synthesis sessions. The worker acknowledges
the requested option during startup. The default remains `0`; no saved settings
or audio route is changed. A public paired trial retained identical output and
reduced observed timing spikes. Separate-process public and private Recording5
parity checks subsequently passed, and a 320-second public callback simulation
played all samples without a stream fault using explicit startup buffering.
Broader sustained speech tests, physical latency, microphone and laptop testing
remain outstanding. This option is still experimental and is not enabled by the
audio app.
