# Optional RVC host integration contract

The existing audio host stays the default. Add an explicit experimental session
choice only after the host path has model-free lifecycle tests; never rewrite
saved model/device/monitor preferences when preparing or stopping that session.

The RVC session must own exactly one RvcProcessStream and RvcCaptureBridge.
Use its fixed 48 kHz mono callback packetizer directly: do not nest it inside
the existing model.convert48 packet queue, which would add another queue and
change the approved timing. Keep monitor output downstream of converted audio,
controlled independently from the game output. No raw microphone fallback.

Before opening any device, validate explicit runtime paths and frozen hashes,
start the owned worker, verify ready acknowledgement, and expose initializing,
ready, stopped and fault states. Cancel initialization and close the complete
owned process tree on stop, host failure or device-open failure. A worker fault
must stop converted output and show the reason; no automatic model substitution.

Keep the existing 400 ms startup / 600 ms maximum queue. Recovery stays off.
The worker profile must explicitly select CPU, frozen features and pitch,
OpenVINO synthesis and existing thread counts. The process execution-speed
request remains false. Do not turn experimental scheduling into global policy.

Required model-free tests before wiring: stop during initialization; device-open
failure closes worker; fault cannot send microphone audio; monitor toggle never
changes game output; session choice does not persist device/routing changes;
callback delegates once without secondary packet queue. Then replay the public
fixtures through the host seam before any microphone/device test.

Evidence so far: private waveform parity and two 900-second public callback
simulation gates passed. Simulated first output is about 540-560 ms; hardware
latency, arbitrary speech, gaming load and XPS remain unvalidated. Explicitly
present those limits in the optional session UI and diagnostic report.
