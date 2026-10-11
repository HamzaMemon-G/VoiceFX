"""Causal pitch + independent cepstral formant shaping, after AI conversion.

Uses MIT stftPitchShift's pitcher/cepster primitives (vendored with license).
Fixed 1024-sample / 64 ms algorithmic delay at 16 kHz; no raw microphone mix.
"""

import sys
import numpy as np

from paths import RESOURCES

sys.path.insert(0, str(RESOURCES / "vendor"))
from stftpitchshift.cepster import lifter
from stftpitchshift.pitcher import shiftpitch
from stftpitchshift.resampler import linear as resample

PRESETS = {
    "AI target / feminine": (0.0, 0.0),
    "Lower / subtle": (-3.0, -1.5),
    "Masculine starting point": (-5.0, -3.0),
    "Deep character": (-8.0, -4.0),
}


class Character:
    def __init__(self):
        self.n = 1024
        self.hop = 128
        self.rate = 16000
        self.window = np.hanning(self.n)
        self.bins = np.arange(self.n // 2 + 1)
        self.prev = np.zeros(len(self.bins))
        self.phase = np.zeros(len(self.bins))
        self.input = np.zeros(self.n)
        self.ola = np.zeros(self.n)
        self.norm = np.zeros(self.n)
        self.pending = np.zeros(0)
        self.output = np.zeros(self.hop)
        self.pitch = 0.0
        self.formant = 0.0
        self.generated = 0

    def frame(self, x, pitch, formant):
        self.input[: -self.hop] = self.input[self.hop :]
        self.input[-self.hop :] = x
        spectrum = np.fft.rfft(self.input * self.window)
        mag = np.abs(spectrum)
        arg = np.angle(spectrum)
        phaseinc = 2 * np.pi * self.hop / self.n
        delta = arg - self.prev - self.bins * phaseinc
        self.prev = arg
        delta = (delta + np.pi) % (2 * np.pi) - np.pi
        frequencies = (self.bins + delta / phaseinc) * (self.rate / self.n)
        # Smooth control changes over several hops; don't reset cached phases.
        self.pitch += 0.25 * (pitch - self.pitch)
        self.formant += 0.25 * (formant - self.formant)
        p = 2 ** (self.pitch / 12)
        q = 2 ** (self.formant / 12)
        neutral = abs(self.pitch) < 1e-3 and abs(self.formant) < 1e-3
        if neutral:
            self.pitch = 0.0
            self.formant = 0.0
            shaped = mag
            new_freq = frequencies
        else:
            encoded = np.maximum(mag, 1e-9)[None, :] + 1j * frequencies[None, :]
            envelope = np.maximum(lifter(encoded, 32)[0], 1e-9)
            encoded.real[0] = mag / envelope
            encoded = shiftpitch(encoded, [p], self.rate)
            shaped = encoded.real[0] * resample(envelope, q)
            new_freq = encoded.imag[0]
            # Match frame energy without amplifying silence or extreme ratios.
            ratio = np.sqrt(np.sum(mag * mag) / max(np.sum(shaped * shaped), 1e-18))
            shaped *= np.clip(ratio, 0.25, 4)
        self.phase = (self.phase + 2 * np.pi * self.hop * new_freq / self.rate) % (
            2 * np.pi
        )
        if neutral:
            self.phase = arg.copy()  # Restore original phase after changing back.
        synthesized = (
            np.fft.irfft(shaped * np.exp(1j * self.phase), n=self.n) * self.window
        )
        self.ola += synthesized
        self.norm += self.window**2
        y = self.ola[: self.hop] / np.maximum(self.norm[: self.hop], 1e-8)
        if self.generated < self.n - self.hop:
            y = np.zeros(self.hop)
        self.generated += self.hop
        self.ola[: -self.hop] = self.ola[self.hop :]
        self.ola[-self.hop :] = 0
        self.norm[: -self.hop] = self.norm[self.hop :]
        self.norm[-self.hop :] = 0
        return y

    def process(self, x, pitch=0, formant=0):
        pitch = float(np.clip(pitch, -12, 6))
        formant = float(np.clip(formant, -6, 4))
        self.pending = np.concatenate((self.pending, np.asarray(x)))
        produced = []
        while len(self.pending) >= self.hop:
            produced.append(self.frame(self.pending[: self.hop], pitch, formant))
            self.pending = self.pending[self.hop :]
        if produced:
            self.output = np.concatenate((self.output, *produced))
        y = self.output[: len(x)].copy()
        self.output = self.output[len(x) :]
        if len(y) != len(x) or not np.isfinite(y).all():
            raise RuntimeError("Invalid character processor output")
        return y.astype(np.float32)
