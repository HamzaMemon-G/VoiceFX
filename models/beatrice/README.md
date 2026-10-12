# Beatrice v2 pilot voices

These are the exact experimental models behind the listening previews selected
on October 12, 2026:

| Voice | Checkpoint step | Preview | Model folder |
| --- | ---: | --- | --- |
| Pop Smoke | 60 | [preview.wav](pop-smoke/preview.wav) | [pop-smoke](pop-smoke/) |
| Opie / Elanip | 80 | [preview.wav](opie/preview.wav) | [opie](opie/) |

The models were trained separately with the official
[Beatrice Trainer](https://huggingface.co/fierce-cats/beatrice-trainer) at revision
`f34836de014b86956096878aecb8d3b17feaaa0b`. Each folder is a complete
Beatrice 2.0.0-rc.0 paraphernalia bundle with a valid portrait and a
`provenance.json` recording the step, source URLs, hashes and training config
hash. The source clips and large optimizer checkpoints are kept out of Git.

**Current status:** These previews received positive listening feedback. VoiceFX
can now load either bundle through a separately installed official Beatrice v2
VST3. Offline 50 ms streaming on the training desktop took about 11–15 ms per
block at the 95th percentile; 100 ms is the fallback for slower CPUs. The XPS and live audio routing are still untested,
and custom names in synthesized greetings remain unreliable. Keep existing
device and Voicemeeter/VBAN settings.

To make checksum-checked import archives for a compatible Beatrice v2 client,
run `python tools/package_beatrice_models.py` from the repository root. The two
ZIPs appear under `dist/beatrice-import/`; the source bundles are untouched.
Importing a model does not configure audio devices or prove live CPU latency.

The models can imitate identifiable public voices. Label generated audio clearly
when sharing it, and use it in ways that respect the speakers and platform rules.
