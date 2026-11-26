# VoiceFX offline training record — 12 October 2026

The training host is a Gigabyte desktop with an NVIDIA GTX 1650 (4 GiB). The
XPS laptop is unavailable. No saved VoiceFX audio devices, Voicemeeter settings
or VBAN routing were changed.

## Pop Smoke

- The target corpus contains 315 seconds of automatically selected interview
  speech for training and 57 seconds held out for validation. Source recordings
  are the [Angie Martinez interview](https://www.youtube.com/watch?v=acAeTc-Vfek)
  and [Apple Music interview](https://www.youtube.com/watch?v=5XcMh4IGLqI).
  Selection is automatic and has not been approved by listening.
- An RVC v2 32 kHz teacher completed 50 epochs in 3844 seconds at batch size 1,
  full precision. The sampled peak system GPU use was 3813 MiB. On one unseen
  input, speaker similarity to the target references changed from 0.872 after
  three epochs to 0.898 after 50 epochs.
- The teacher rendered 97 training pairs and 10 held-out pairs from public host
  speech. A matching LLVC student was fine-tuned from the pinned upstream
  checkpoint with spectral and speaker losses. Its best current checkpoint is
  an experimental CPU-compatible candidate. On the same unseen input, target
  speaker similarity was 0.881; desktop CPU processing took about 25 ms at
  the 104 ms chunk setting. A small speech recognizer retained much of the
  wording but made several errors. Subjective quality and XPS performance are
  not yet verified.
- [What You Know Bout Love](https://www.youtube.com/watch?v=7Mzxotj6Gvs)
  and [Dior](https://www.youtube.com/watch?v=goYgHnsQdtY) were downloaded from
  the official artist channel and separated into vocal stems. Neither yielded
  clips that met the conservative interview-speaker threshold. Both remain
  excluded from training.
- A controlled pitch/F0 sweep on one unseen sentence favored the original
  `-12/pm` setting for target-voice similarity (0.898). `-10/pm` improved that
  sentence's small-ASR transcript but lowered similarity to 0.883. A separate
  `-10` student on curated pairs did not improve the automatic voice-match or
  transcript checks, so the original candidate remains selected.
- A full paired-data ASR audit found two extremely repetitive source clips and
  one corrupted validation conversion. Curated manifests exclude them without
  deleting source files. A short Pop student retrain on the curated set did
  not clearly beat the existing candidate.
- A [Tim Westwood interview](https://www.youtube.com/watch?v=URJGVMqOX4Y)
  was separately screened against both Pop voice references and inferred
  interviewer turns. A high-confidence subset added 78 seconds to training
  and 15 seconds to held-out validation in an expanded RVC experiment. That
  warm-started eight-epoch experiment completed in 807 seconds with sampled
  peak system GPU use of 3684 MiB. It did not improve generalization: across
  nine held-out host-speech clips, mean target-speaker similarity fell from
  0.888 to 0.857, while small-ASR word-sequence agreement with the inputs fell
  from 0.629 to 0.557. The original teacher and CPU student remain selected.

## Opie / Elanip

- Three channel recordings yielded 333 seconds of automatically selected
  speech for training and 72 seconds held out. Other people speak in these
  videos; clip selection has not been approved by listening.
- A first 10-epoch RVC trial on the initial 102 seconds completed. On one unseen
  input, speaker similarity to withheld Opie references rose from 0.625 for the
  source to 0.777 for the converted voice. An expanded 30-epoch RVC run from
  this checkpoint completed in 2942 seconds, with sampled peak system GPU use
  of 3674 MiB. Similarity on the same unseen input improved to 0.810.
- The expanded teacher rendered 97 training pairs and ten held-out pairs from
  isolated host speech. A separate LLVC student was trained with spectral and
  speaker losses. A 50:50 weight blend of its final two checkpoints balanced
  automatic voice-match and intelligibility checks: similarity to Opie on the
  unseen input was 0.753, and mean teacher-student similarity across ten held-out
  clips was 0.850. Desktop CPU processing took about 23 ms at the 104 ms chunk
  setting. A small speech recognizer still made wording errors; subjective
  quality and XPS performance remain unverified.
- A paired-data ASR audit excluded the same two repetitive source clips from
  an Opie retrain. It marginally improved automatic voice-match but worsened
  the test-sentence transcript, so the previous Opie candidate remains selected.

## Runtime and provenance

VoiceFX now has an optional independent headphone monitor and local custom
LLVC model selection with checksum verification. Turning off the monitor leaves
the voice destination active. Voicemeeter-controlled headphone monitoring is
outside this control.

The pinned upstream revisions are RVC
`81eed5e8f68b6bed1789f682fe78cdd324495afc` and LLVC
`1627c5d358cf9bb2b92b0ccc513d8b36807c923d`. The RVC training copy uses
`foreach=False` on its two AdamW optimizers to fit the 4 GiB GPU. The
experiment bundle contains the source URLs, manifests, checksums, scripts,
configuration records and that small patch. Original copyrighted recordings
are not packaged.
