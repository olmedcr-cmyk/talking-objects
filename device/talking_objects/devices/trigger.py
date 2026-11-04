"""What starts and ends a conversation: a handset, a button, a sensor.

`gpio`      a switch on a GPIO pin (pull-up). Released = start, pressed = end,
            which is how a phone hook behaves. TRIGGER_INVERT=1 swaps them.
`keyboard`  development without hardware: 's' + Enter starts, 'e' + Enter ends.
`auto`      no switch at all: talk, rest, talk again. A safety net for when
            the switch breaks and the piece still has to work.

On a Raspberry Pi 5 gpiozero works on top of `lgpio` (the RP1 chip changed
pin access); `deploy/install.sh` installs python3-lgpio.
"""

from __future__ import annotations

import asyncio
import logging
import sys
from collections.abc import Callable

from ..config import TriggerConfig

log = logging.getLogger("talking_objects.trigger")


class Trigger:
    def __init__(
        self,
        cfg: TriggerConfig,
        on_start: Callable[[], None],
        on_end: Callable[[], None],
        max_call_s: float = 600,
    ) -> None:
        self.cfg = cfg
        self.on_start = on_start
        self.on_end = on_end
        self.max_call_s = max_call_s
        self._button = None
        self._loop: asyncio.AbstractEventLoop | None = None
        self._task: asyncio.Task | None = None

    def start(self) -> None:
        self._loop = asyncio.get_running_loop()
        if self.cfg.mode == "auto":
            log.warning("AUTO mode: conversations in a loop, %.0f s rest", self.cfg.auto_pause_s)
            self._task = asyncio.create_task(self._auto())
        elif self.cfg.mode == "keyboard":
            log.warning("KEYBOARD mode: 's' + Enter starts, 'e' + Enter ends")
            self._task = asyncio.create_task(self._keyboard())
        else:
            from gpiozero import Button

            self._button = Button(self.cfg.pin, pull_up=True, bounce_time=self.cfg.bounce_ms / 1000)
            released, pressed = (self.on_end, self.on_start) if self.cfg.invert else (self.on_start, self.on_end)
            self._button.when_released = lambda: self._emit(released)
            self._button.when_pressed = lambda: self._emit(pressed)
            log.info("trigger on GPIO%d (debounce %d ms)", self.cfg.pin, self.cfg.bounce_ms)

    def stop(self) -> None:
        if self._task is not None:
            self._task.cancel()
            self._task = None
        if self._button is not None:
            self._button.close()
            self._button = None

    def _emit(self, callback: Callable[[], None]) -> None:
        # gpiozero calls back from its own thread.
        if self._loop is not None:
            self._loop.call_soon_threadsafe(callback)

    async def _auto(self) -> None:
        await asyncio.sleep(3)
        while True:
            self.on_start()
            await asyncio.sleep(self.max_call_s)
            self.on_end()
            await asyncio.sleep(self.cfg.auto_pause_s)

    async def _keyboard(self) -> None:
        loop = asyncio.get_running_loop()
        while True:
            line = await loop.run_in_executor(None, sys.stdin.readline)
            if not line:
                await asyncio.sleep(0.2)
                continue
            command = line.strip().lower()
            if command in ("s", "start"):
                self.on_start()
            elif command in ("e", "end"):
                self.on_end()
