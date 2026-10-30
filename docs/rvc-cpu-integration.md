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

Follow-up reliability checks on two held-out public speakers underflowed after
approximately 51 and 116 seconds. Neither completed its planned ten minutes.
Consequently the earlier 320-second pass does not establish general reliability;
the experimental backend remains unsuitable for an approved live release.

An additional explicit `synthesis_backend="openvino"` experiment keeps the exact
approved TorchScript feature path and pitch processing. It compiles only the
checksum-verified synthesis graph for CPU, forcing FP32 accuracy mode and
disabling dynamic quantization. An isolated OpenVINO package path is required;
the default remains `"ort"`. The child must acknowledge the requested backend.
Public complete-waveform tests with matched synthesis noise passed on three
clips, with maximum error below `1e-5`. Private process parity and sustained
callback tests are pending; this is not an enabled or approved live mode.

The separate OpenVINO *feature* experiment failed the full-waveform accuracy gate
on one held-out clip and is rejected. It is not used by this synthesis option.

Follow-up synthesis-only testing passed private Recording5 process parity. One
held-out speaker completed 600 seconds of simulated playback; the other still
underflowed after about 72 seconds. The improvement does not yet establish
general reliability. A targeted follow-up combines this faster synthesis path
with an explicit `worker_priority="above_normal"` trial. This option changes only
the newly created Windows worker's scheduling class, verifies it with Windows,
and ends with that process. The default remains `"normal"`; other processes and
system settings are not changed. It is not a production default or gaming test.

`app/rvc_capture_bridge.py` assembles nondividing mono capture callback sizes into
complete model packets and reads corresponding output without model or pipe I/O
in the callback. It discards pre-ready capture, rejects invalid channels/samples,
and performs no gain, character processing, device selection or routing. It is
offline-tested and is not wired to the application's audio host yet.

The synthesis-only, above-normal worker subsequently underflowed on both public
ten-minute trials, after approximately 560 and 482 seconds. Scheduling changes
therefore do not establish reliable playback. No live mode has been enabled.

An explicit `recover_underflow=True` diagnostic selects `TimelineAudioBuffer`;
the default remains `False` and keeps the original fault-on-underflow behavior.
Recovery preserves the existing queue limits and output timeline. Missing audio
is replaced with silence, counted as `missing_samples`, and never replayed later.
Late packets are trimmed or discarded at their original sample positions;
`late_discarded_samples` records that loss. `underflow_events` counts callbacks
that contained missing samples, rather than distinct contiguous outage periods.
Corrupt packets, transport failures and queue overflow still stop the stream.

This option handles a dropout without permanently stopping otherwise valid
processing; it does not make model computation faster or satisfy zero-loss live
performance requirements. Healthy private Recording5 process output retained
the same maximum waveform difference of approximately `3.714e-5`, with zero
missing samples before an intentional underflow probe. Public sustained recovery
diagnostics report sample loss separately from completion. A run with any missing
samples must not be described as a reliability pass. No microphone, physical
latency, gaming or XPS validation is implied.

The two recovery trials each reached 600 seconds, but neither passed zero-loss
reliability. LibriSpeech lost 182,400 samples (3.80 seconds, 0.633% of playback);
VOiCES lost 167,040 samples (3.48 seconds, 0.580%). The missing portions became
silence, and equal numbers of late samples were discarded. These losses occurred
in 190 and 174 callbacks respectively; they are not counts of distinct outages.
First playback was approximately 340 and 360 ms after the first complete 200 ms
input packet. That timing excludes the initial capture packet and additional
model alignment and hardware delay. The results demonstrate bounded recovery,
not acceptable uninterrupted live speech. Defaults and audio routes remain
unchanged. Further offline work attributes stalls to individual model stages
and CPU service before selecting another optimization.

`app/rvc_cpu_check.py` is an opt-in, file-driven check for another CPU when the
runtime dependencies and model paths are available. It opens no audio devices,
changes no saved settings and stores reports and timings, rather than source
audio. It accepts a mono 16-bit PCM WAV at 16 or 48 kHz. The source repeats for
the requested duration; repetition is a workload test, not a test of new words.
Its 20 ms simulated capture callbacks exercise the actual capture bridge and
separate worker. The first complete model packet arrives after 200 ms of
simulated capture, so capture-start and post-packet timing are distinguished.

Run `python app/rvc_cpu_check.py --help` for explicit source, snapshot, RVC and
package paths. Defaults remain ORT, normal worker priority and dynamic-work
option zero. OpenVINO and other experimental options must be requested
explicitly. Reports preserve the source SHA, runtime options, all observed
completed-packet timings, faults, startup timing and shutdown outcome. Existing
report files are never overwritten. A finished run can still fail: the checker
requires uninterrupted playback, model p95 at most 160 ms per 200 ms packet and
callback work within 20 ms. It does not drain the live queue at the end and does
not claim that queued tail audio played. A simulated pass still requires sound,
sustained-load, microphone and physical-latency validation on the target machine.

`app/rvc_cpu_fixture_check.py` separately checks numerical portability against a
checksum-pinned public input and reference array, through the actual child
process. It restarts the worker for each case to reset caches and random noise.
It opens no devices and preserves private recordings. Reference parity requires
maximum complete-waveform difference below `1e-4` and verified worker shutdown;
it is unpaced and cannot establish CPU throughput or physical latency. Public
fixtures retain source attribution and are separate from private sound snapshots.

The clean CPU-only environment passed both public complete-waveform fixtures
exactly, but its paced tests still underflowed after about 30 and 160 seconds.
Changing from the training CUDA wheel to the CPU wheel did not establish live
reliability. The second run also reported a transport shutdown failure.

Windows cleanup now owns the newly created worker and its descendants in a
private kill-on-close job. The worker starts suspended, joins that job, then
resumes; a virtual-environment launcher cannot create an unowned child first.
This prevents an inherited stdout handle in a descendant from keeping the
reader alive after the launcher exits. The receive wait is cancellable, and
cleanup checks reader termination rather than blocking on its text-pipe lock.
Only this worker tree is affected. Regressions cover a descendant holding stdout
and shutdown during an in-flight conversion. This fixes a lifecycle failure
path; it does not reduce model computation or establish uninterrupted playback.

The optional local diagnostic bundle can include its own CPU-only interpreter,
dependencies and attributed public fixtures. `app/rvc_cpu_portable_entry.py`
runs the reference check before either timing sample, owns its checker processes
in Windows jobs, and writes results in a new timestamped folder. It never selects
the live backend or opens audio devices. Its launcher clears inherited Python
paths and disables user-site packages; bundle validation must prove the relocated
interpreter and Torch library load from that folder. Packaging success and
public reference parity remain separate from the timed CPU gates and target
hardware validation. The bundle and model payload remain local.

The completed local bundle passed relocated-interpreter and public waveform
checks, its user entry point, worker cleanup, archive SHA and archive CRC checks.
Its timed desktop samples still underflowed after about 244 and 286 seconds;
packaging success therefore does not make it a usable live release.

The routine-log IO hypothesis was rejected. Upstream inference already limits
its status messages to the first three calls and every hundredth call. The
paired test retained identical waveforms but observed only four write calls
and 109 bytes in the verbose intervals. Its small timing difference does not
establish useful headroom, and no logging suppression was adopted.

A separate experimental `disable_execution_throttling=True` option tests a
specific host/service boundary: the existing audio host requests execution-speed
throttling be disabled for its own process, while a separate inference service
must make its own request explicitly rather than assume the launcher's state.
The default remains `False`. The service applies and reads back the hint in its
actual Python worker, acknowledges its PID and masks during startup, and the
controller rejects an unacknowledged request. Only the execution-speed bit of
that owned process is changed; other bits are preserved. No global power plan,
registry, security setting or other process is changed, and the request ends
with the worker. An initial zero mask means system-managed policy, not evidence
that the worker was being throttled. Readback is not a measured clock speed.

The requested mode passed both complete public fixture waveforms exactly and
verified shutdown. Thirty-five contract tests pass, including unchanged parent
state after a child-only request and rejection of a missing acknowledgement.
Opposite-order speaker trials compare requested and default modes with identical
models, queues, thread counts and existing worker priority. Timing remains
unapproved; the option is not enabled in the audio app or packaged baseline.
