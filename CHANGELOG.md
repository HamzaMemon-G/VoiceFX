# Changelog

## Unreleased

- Replace the vulnerable optional app PyTorch2.5.1 pin with CPU-only2.15.0.
  Keep experimental RVC dependencies isolated and frozen runtime assets intact.
  This removes the old pin affected by
  [GHSA-53q9-r3pm-6pq6](https://github.com/pytorch/pytorch/security/advisories/GHSA-53q9-r3pm-6pq6),
  which bypasses `weights_only=True` in vulnerable checkpoint loaders.

- Keep headphone self-monitoring independent of game output. Preserve historical
  Beatrice Pop60/Opie80 pilot bundles and checksum verification.
- Add an optional separate-process CPU RVC host, bounded transport, scoped worker
  cleanup, explicit device/session admission and offline diagnostic commands.
- Support a separately selected experimental1000ms startup queue without changing
  the normal app defaults or saved routing. Document failed headroom checks and
  distinguish simulated first output from physical latency.
- Reject malformed/nonfinite native audio before it reaches stateful DSP; handle
  failed resets, invalid native modes and null buffers safely. Clamp native
  controls to supported UI ranges.
- Run the full device-free suite in CI, including RVC lifecycle/cleanup contracts
  and tests against the freshly compiled C++ DLL.
- Allow isolated build output paths and put dependency notices in the matching
  distribution. Extend ignores for credentials, private audio and runtime exports.

No new release is prepared: CPU headroom, physical microphone latency and target
XPS/gaming reliability remain unvalidated. Local build checks are not release
approval. Existing v0.1.0 remains unchanged.
