"""A 20x4 character LCD (HD44780 with a PCF8574 I2C backpack).

Find its address with `i2cdetect -y 1` (usually 0x27 or 0x3F) and set
LCD_ADDRESS. Without RPLCD or without a screen, it degrades to a no-op.
"""

from __future__ import annotations

import logging
import textwrap
import unicodedata
from typing import Any

log = logging.getLogger("talking_objects.display")

COLS, ROWS = 20, 4


def _plain(text: str) -> str:
    # The HD44780 character ROM has no accents: strip them rather than
    # printing garbage.
    return unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode()


def validate_message(args: dict[str, Any]) -> dict[str, Any]:
    text = str(args.get("text", "")).strip()
    if not text:
        raise ValueError("text is empty")
    return {"text": text[: COLS * ROWS]}


def layout(text: str) -> list[str]:
    lines = textwrap.wrap(_plain(text).upper(), COLS)[:ROWS]
    return [line.ljust(COLS) for line in lines] + [" " * COLS] * (ROWS - len(lines))


class Display:
    def __init__(self, address: int | None) -> None:
        self.address = address
        self._lcd = None
        self.lines: list[str] = layout("")

    def open(self) -> None:
        if self.address is None:
            log.info("no LCD_ADDRESS: no screen")
            return
        try:
            from RPLCD.i2c import CharLCD

            self._lcd = CharLCD("PCF8574", self.address, cols=COLS, rows=ROWS)
            self._lcd.clear()
        except Exception:
            log.exception("could not open the LCD; messages are ignored")
            self._lcd = None

    async def show(self, args: dict[str, Any]) -> None:
        """Action handler: `{"text": "I AM LISTENING"}`."""
        self.lines = layout(args["text"])
        if self._lcd is not None:
            self._lcd.cursor_pos = (0, 0)
            self._lcd.write_string("".join(self.lines))
