"""Small, vectorised audio helpers. 16-bit little-endian PCM everywhere."""

from __future__ import annotations

import numpy as np


def silence(n_bytes: int) -> bytes:
    return bytes(n_bytes)


def rms(pcm: bytes) -> float:
    if not pcm:
        return 0.0
    x = np.frombuffer(pcm, dtype=np.int16).astype(np.float32)
    return float(np.sqrt(np.mean(x * x))) if x.size else 0.0


def apply_gain(pcm: bytes, gain: float) -> bytes:
    if gain == 1.0 or not pcm:
        return pcm
    x = np.frombuffer(pcm, dtype=np.int16).astype(np.float32) * gain
    return np.clip(x, -32768, 32767).astype(np.int16).tobytes()


class Ducker:
    """Lowers the microphone while the speaker is playing.

    Without it the agent hears itself through the speaker and its own voice
    activity detection cuts it off mid-sentence. Raise the depth if it still
    interrupts itself; lower it if it is hard to talk over.
    """

    def __init__(self, depth_db: float = 12.0, threshold: float = 300.0) -> None:
        self.threshold = threshold
        self.set_depth(depth_db)

    def set_depth(self, db: float) -> None:
        self.depth_db = max(0.0, db)
        self._gain = 10 ** (-self.depth_db / 20)

    def process(self, near: bytes, far_rms: float) -> bytes:
        return apply_gain(near, self._gain) if far_rms > self.threshold else near


def _lowpass(taps: int, cutoff: float) -> np.ndarray:
    n = np.arange(taps) - (taps - 1) / 2
    h = np.sinc(2 * cutoff * n) * np.hamming(taps)
    return (h / h.sum()).astype(np.float32)


class _Filter:
    """FIR filter that keeps its tail between blocks, so blocks join cleanly."""

    def __init__(self, h: np.ndarray) -> None:
        self.h = h
        self.tail = np.zeros(len(h) - 1, dtype=np.float32)

    def __call__(self, x: np.ndarray) -> np.ndarray:
        y = np.convolve(np.concatenate([self.tail, x]), self.h, mode="valid")
        self.tail = np.concatenate([self.tail, x])[-(len(self.h) - 1):]
        return y


class Downsampler48to16:
    """48 kHz -> 16 kHz, what ElevenLabs' SDK speaks."""

    def __init__(self) -> None:
        self._f = _Filter(_lowpass(63, 1 / 6))
        self._phase = 0

    def process(self, pcm: bytes) -> bytes:
        x = np.frombuffer(pcm, dtype=np.int16).astype(np.float32)
        y = self._f(x)
        start = (-self._phase) % 3
        out = y[start::3]
        self._phase = (self._phase + len(x)) % 3
        return np.clip(out, -32768, 32767).astype(np.int16).tobytes()


class Upsampler16to48:
    """16 kHz -> 48 kHz for the sound card."""

    def __init__(self) -> None:
        self._f = _Filter(_lowpass(63, 1 / 6) * 3)

    def process(self, pcm: bytes) -> bytes:
        x = np.frombuffer(pcm, dtype=np.int16).astype(np.float32)
        stuffed = np.zeros(len(x) * 3, dtype=np.float32)
        stuffed[::3] = x
        y = self._f(stuffed)
        return np.clip(y, -32768, 32767).astype(np.int16).tobytes()
