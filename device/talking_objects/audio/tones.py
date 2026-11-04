"""Waiting tones: silence while connecting reads as a broken object.

A ringback tone turns the second or two the provider (or the fallback) needs
into part of the fiction. 425 Hz is the European ringback frequency.
"""

from __future__ import annotations

import asyncio

import numpy as np

RINGBACK_HZ = 425
RING_ON_S = 1.0
RING_OFF_S = 2.0


def tone(seconds: float, freq: float = RINGBACK_HZ, rate: int = 48000, level: float = 0.18) -> bytes:
    n = int(seconds * rate)
    t = np.arange(n) / rate
    wave = np.sin(2 * np.pi * freq * t)
    # 10 ms fades so the tone does not click.
    fade = min(n // 2, int(0.01 * rate))
    if fade:
        ramp = np.linspace(0, 1, fade)
        wave[:fade] *= ramp
        wave[-fade:] *= ramp[::-1]
    return (wave * level * 32767).astype(np.int16).tobytes()


async def ringback(play, rate: int = 48000) -> None:
    """Play ringback through `play(pcm)` until cancelled."""
    on = tone(RING_ON_S, rate=rate)
    while True:
        play(on)
        await asyncio.sleep(RING_ON_S + RING_OFF_S)
