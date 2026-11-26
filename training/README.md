# Offline custom voice training

Training belongs on the GTX 1650 desktop in its own environment. VoiceFX on
the XPS stays CPU-only. Keep its saved audio devices and existing Voicemeeter
and VBAN routing. None of the files here opens an audio device or changes routing.

## Current readiness (12 October 2026)

The inspected machine is a Gigabyte H310M S2 2.0 desktop with approximately
16 GiB RAM and a GTX 1650 with 4096 MiB VRAM. NVIDIA driver 616.56 detects it;
approximately 3488 MiB was free at the initial snapshot. Free memory varies.
An isolated Python 3.12.15 environment with PyTorch 2.7.1+cu118 passed CUDA
backward execution. Pop Smoke's RVC teacher completed 50 epochs (about 64
minutes) with sampled peak GPU usage of 3813 MiB. Opie's first 10-epoch RVC
trial and a 30-epoch expanded run completed; its sampled peak GPU usage was
3674 MiB. These measurements
describe this desktop.
The automatically filtered Pop Smoke candidate contains 315 seconds of training
speech and 57 seconds held out for validation. Clips have not been manually
listening-approved. Two official Pop Smoke songs were separated and screened,
but no clips passed the conservative interview-speaker threshold, so their
vocals were excluded. The Opie candidate from three videos has 333 seconds of
training and 72 seconds of validation speech.

Experimental Pop Smoke and Opie LLVC students now load in VoiceFX's CPU
streaming adapter. On one unseen clip, target-speaker cosine similarity was
0.881 for Pop Smoke versus 0.898 for its RVC teacher, and 0.753 for Opie versus
0.810 for its teacher. Desktop CPU streaming checks took about 25 ms and 23 ms
respectively at the 104 ms chunk setting. Automatic speech recognition still
makes wording errors. These checks do not establish natural-sounding speech or
XPS performance: the XPS is unavailable.

## Model path

VoiceFX retains two pinned, checksummed built-in LLVC checkpoints. It can also
list separately installed Pop Smoke and Opie LLVC checkpoints with SHA-256
verification and strict weight loading. It cannot load an RVC checkpoint
directly.

1. Prepare clean target-speaker recordings. For the Pop Smoke target, prioritize
   isolated spoken voice rather than music, backing vocals, or heavy reverb.
   Listen to extracted vocals before accepting them. Keep evaluation clips
   separate from training clips. RVC upstream recommends at least 10 minutes
   of low-noise speech; duration alone does not establish dataset quality.
2. Train an RVC teacher offline on the desktop. The first Pop Smoke run used
   32 kHz, batch size 1, short clips, no GPU dataset cache and full precision.
   Compare candidate checkpoints on held-out inputs before expanding.
3. Use that teacher to create paired original/converted speech from multiple
   source speakers. LLVC requires paired data in train/dev/val folders.
4. Fine-tune the compatible LLVC student on these pairs. The current experiment
   uses paired spectral and speaker losses with an upstream initialization;
   it is not the full upstream adversarial and Fairseq recipe. Keep separate
   held-out scores and listening samples to decide if it is usable.
5. Register only an approved LLVC checkpoint through VoiceFX's custom model
   manifest. Built-in model files and checksums remain unchanged.
6. Benchmark the student on the XPS using the existing buffer/deadline checks
   before selecting it for real-time use. Transfer only the approved checkpoint
   and configuration; training remains on the desktop.

## Separate environment and check

Do not install GPU packages into the XPS VoiceFX environment. Current RVC main
targets Python 3.12 and documents CUDA 11.8 packages for pre-RTX-50 NVIDIA cards.
Upstream LLVC documents Python 3.11; use a separate environment for that stage.
Pin the upstream revision and record installed dependencies for each run.
One-time code, pretrained weights, and dependency downloads are needed before
training can operate fully offline.

Run the read-only check with whichever training interpreter you have prepared:

```powershell
python training/check_gpu.py
# In a prepared CUDA environment, fail if backward execution does not work:
python training/check_gpu.py --require-cuda
```

This reports driver memory and runs a small CUDA backward pass when PyTorch is
available. Passing it does not prove RVC or LLVC fits in 4 GiB. Review the
candidate dataset and validation audio before accepting a trained model.

Sources:
- https://github.com/RVC-Project/Retrieval-based-Voice-Conversion-WebUI
- https://github.com/KoeAI/LLVC (training and paired dataset instructions)
