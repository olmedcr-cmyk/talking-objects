"""An addressable LED strip (WS2812 / WS2812E) driven over SPI.

On a Raspberry Pi 5 the classic `rpi_ws281x` library does NOT work: it relies
on the DMA/PWM of the BCM chips in Pi 0-4, and the Pi 5 uses RP1. The working
route is to encode each WS2812 bit as SPI bits on MOSI (GPIO10).

Electrical requirements, outside software:
  - A separate 5 V supply. 60 px at full white draw about 3.6 A; the Pi's
    rail cannot give that. Common ground with the Pi.
  - Logic level: the strip expects ~3.5 V and the Pi gives 3.3 V. A
    74AHCT125 buffer solves it. Without it, it works intermittently, which in
    an installation that runs for weeks means it does not work.

Without the library (a Mac), everything degrades to a no-op and is logged:
a light can never raise an exception into the conversation.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from ..config import LedConfig

log = logging.getLogger("talking_objects.leds")

try:  # pragma: no cover - only on the Pi
    import board
    import neopixel_spi
except Exception as exc:
    board = None
    neopixel_spi = None
    _IMPORT_ERROR: Exception | None = exc
else:
    _IMPORT_ERROR = None

NAMED_COLORS: dict[str, tuple[int, int, int]] = {
    "white": (255, 255, 255),
    "warm": (255, 150, 60),
    "red": (210, 25, 15),
    "green": (30, 190, 70),
    "blue": (30, 90, 220),
    "amber": (230, 120, 10),
    "violet": (140, 60, 220),
    "off": (0, 0, 0),
}
EFFECTS = ("solid", "breathe", "pulse")


def validate_light(args: dict[str, Any]) -> dict[str, Any]:
    """Normalise a light request. Unknown colors and effects are refused."""
    color = str(args.get("color", "warm")).lower()
    if color not in NAMED_COLORS:
        raise ValueError(f"unknown color {color!r}; use one of {', '.join(NAMED_COLORS)}")
    effect = str(args.get("effect", "solid")).lower()
    if effect not in EFFECTS:
        raise ValueError(f"unknown effect {effect!r}; use one of {', '.join(EFFECTS)}")
    seconds = float(args.get("seconds", 6))
    return {"color": color, "effect": effect, "seconds": max(0.5, min(seconds, 60.0))}


class Leds:
    def __init__(self, cfg: LedConfig) -> None:
        self.cfg = cfg
        self._pixels = None
        self._animation: asyncio.Task | None = None
        self.current: tuple[int, int, int] = (0, 0, 0)

    def open(self) -> None:
        if neopixel_spi is None:
            log.warning("LEDs unavailable (%s); light orders are ignored", _IMPORT_ERROR)
            return
        try:
            self._pixels = neopixel_spi.NeoPixel_SPI(
                board.SPI(), self.cfg.count, pixel_order=neopixel_spi.GRB,
                brightness=self.cfg.brightness, auto_write=False,
            )
            # A freshly powered strip shows whatever garbage is in its
            # registers until the first frame: clear it explicitly.
            self._fill((0, 0, 0))
            self.idle()
            log.info("%d LEDs ready over SPI", self.cfg.count)
        except Exception:
            log.exception("could not open the strip; light orders are ignored")
            self._pixels = None

    def _fill(self, rgb: tuple[int, int, int]) -> None:
        self.current = rgb
        if self._pixels is not None:
            self._pixels.fill(rgb)
            self._pixels.show()

    def warn(self) -> None:
        """Steady amber: the object is on but cannot talk (e.g. no audio)."""
        self._cancel()
        self._fill(NAMED_COLORS["amber"])

    def idle(self) -> None:
        self._cancel()
        self._fill(self.cfg.idle_color or (0, 0, 0))

    def _cancel(self) -> None:
        if self._animation is not None:
            self._animation.cancel()
            self._animation = None

    async def light(self, args: dict[str, Any]) -> None:
        """Action handler: `{"color": "blue", "effect": "breathe", "seconds": 6}`."""
        self._cancel()
        rgb = NAMED_COLORS[args["color"]]
        self._animation = asyncio.create_task(self._play(rgb, args["effect"], args["seconds"]))

    async def _play(self, rgb: tuple[int, int, int], effect: str, seconds: float) -> None:
        try:
            if effect == "solid":
                self._fill(rgb)
                await asyncio.sleep(seconds)
            else:
                period = 2.4 if effect == "breathe" else 0.6
                steps = 24
                elapsed = 0.0
                while elapsed < seconds:
                    for i in range(steps):
                        k = 0.15 + 0.85 * (1 - abs(1 - 2 * i / steps))
                        self._fill(tuple(int(c * k) for c in rgb))
                        await asyncio.sleep(period / steps)
                    elapsed += period
            self._fill(self.cfg.idle_color or (0, 0, 0))
        except asyncio.CancelledError:
            pass
