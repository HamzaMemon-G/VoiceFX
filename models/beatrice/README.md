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

**Current status:** These previews received positive listening feedback, but
have not been tested as a live stream or on the XPS. VoiceFX's current AI engine
loads LLVC checkpoints, not Beatrice bundles. Use a compatible Beatrice 2.0.0-rc.0
client to audition these bundles until a Beatrice runtime is integrated and
benchmarked in VoiceFX. Keep existing device and Voicemeeter/VBAN settings.

The models can imitate identifiable public voices. Label generated audio clearly
when sharing it, and use it in ways that respect the speakers and platform rules.
