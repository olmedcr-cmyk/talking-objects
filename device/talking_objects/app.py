"""The object: wires trigger, audio, providers, actions, reactor and link.

    trigger ──▶ App ──▶ FailoverProvider ──▶ Vidiv (LiveKit) | ElevenLabs
                 │
         AudioDevice (one thread owns the card)
                 │
                Bus ──▶ Reactor ──▶ ActionRegistry ──▶ LEDs, LCD, …
                 │                        ▲
                 └──▶ status page         └── Link ◀── Worker (MCP)
"""

from __future__ import annotations

import asyncio
import logging
import socket
from typing import Any

from .actions import ActionRegistry, Budget
from .audio.device import AudioDevice, AudioUnavailable
from .audio.tones import ringback
from .bus import Bus
from .config import Settings
from .devices.display import Display, validate_message
from .devices.leds import EFFECTS, NAMED_COLORS, Leds, validate_light
from .devices.trigger import Trigger
from .link import Link
from .providers.failover import AllProvidersFailed, FailoverProvider
from .reactor import Reactor, load_rules

log = logging.getLogger("talking_objects.app")

LIGHT_SCHEMA = {
    "type": "object",
    "properties": {
        "color": {"type": "string", "enum": list(NAMED_COLORS)},
        "effect": {"type": "string", "enum": list(EFFECTS)},
        "seconds": {"type": "number", "minimum": 0.5, "maximum": 60},
    },
    "required": ["color"],
    "additionalProperties": False,
}
MESSAGE_SCHEMA = {
    "type": "object",
    "properties": {"text": {"type": "string", "maxLength": 80}},
    "required": ["text"],
    "additionalProperties": False,
}


def build_providers(settings: Settings, audio: AudioDevice, bus: Bus) -> FailoverProvider:
    providers: dict[str, Any] = {}
    mode = settings.failover.mode
    if mode in ("auto", "vidiv") and settings.vidiv.ready:
        from .providers.vidiv import VidivProvider

        providers["vidiv"] = VidivProvider(settings.vidiv, audio)
    if mode in ("auto", "elevenlabs") and settings.elevenlabs.ready:
        from .providers.elevenlabs import ElevenLabsProvider

        providers["elevenlabs"] = ElevenLabsProvider(settings.elevenlabs, audio)
    return FailoverProvider(providers, settings.failover, bus=bus)


class App:
    def __init__(self, settings: Settings, *, provider=None, audio: AudioDevice | None = None) -> None:
        self.settings = settings
        self.bus = Bus()
        self.audio = audio or AudioDevice(settings.audio, null=settings.fake_audio)
        self.actions = ActionRegistry(bus=self.bus)
        self.leds = Leds(settings.leds)
        self.display = Display(settings.lcd_address)
        self.provider = provider or build_providers(settings, self.audio, self.bus)
        self.reactor = Reactor(load_rules(settings.rules_path), self.actions)
        self.link = Link(settings.link_url, self.actions, device_id=socket.gethostname(),
                         on_context=self.provider.set_context)
        self.trigger = Trigger(settings.trigger, self.on_start, self.on_end, settings.max_call_s)
        self.state = "idle"
        self.audio_ok = False
        self.transcript: list[dict[str, str]] = []
        self._call: asyncio.Task | None = None
        self._end = asyncio.Event()
        self._register_actions()
        self.bus.subscribe("action", lambda _t, p: asyncio.ensure_future(
            self.link.send({"type": "event", "topic": "action", "name": p["name"],
                            "source": p["source"]})))

    def _register_actions(self) -> None:
        self.actions.register(
            "light", self.leds.light,
            description="Change the object's light to underline a moment of the "
                        "conversation. Use it sparingly, when the mood shifts.",
            schema=LIGHT_SCHEMA, validate=validate_light, budget=Budget(cooldown_s=2),
        )
        self.actions.register(
            "show_message", self.display.show,
            description="Write a short phrase (up to 80 characters) on the "
                        "object's screen, as if it were thinking aloud.",
            schema=MESSAGE_SCHEMA, validate=validate_message,
            budget=Budget(per_call=4, cooldown_s=8),
        )

    # -- lifecycle ----------------------------------------------------------
    async def run(self) -> None:
        for warning in self.settings.warnings:
            log.warning(warning)
        self.leds.open()
        self.display.open()
        try:
            self.audio.start()
            self.audio_ok = True
        except AudioUnavailable as exc:
            # Do not die: a dead process under systemd shows nothing to
            # anyone. Stay up, say it, and refuse to start conversations.
            log.error("no audio (%s); conversations are disabled", exc)
        self.link.start()
        self.trigger.start()
        await self.provider.prefetch()
        log.info("ready (%s)", ", ".join(self.provider.order()) or "no provider")
        await asyncio.Event().wait()

    def on_start(self) -> None:
        if self._call is not None and not self._call.done():
            return
        if not self.audio_ok:
            log.warning("trigger ignored: no audio")
            self.leds.warn()
            return
        self._end.clear()
        self._call = asyncio.create_task(self._converse())

    def on_end(self) -> None:
        self._end.set()

    def _heard(self, speaker: str, text: str) -> None:
        self.bus.publish("transcript", speaker=speaker, text=text)
        if self.settings.store_transcripts:
            self.transcript.append({"speaker": speaker, "text": text})
        self.reactor.hear(speaker, text)

    async def _converse(self) -> None:
        self.actions.new_call()
        self.reactor.new_call()
        self.transcript.clear()
        self._set_state("connecting")
        session = None
        ringing = asyncio.create_task(ringback(self.audio.play, self.settings.audio.sample_rate))
        try:
            try:
                session = await self.provider.start(self.actions, on_transcript=self._heard)
            finally:
                ringing.cancel()
                self.audio.flush_output()
            self._set_state("talking")
            ended = asyncio.create_task(self._end.wait())
            closed = asyncio.create_task(session.wait_closed())
            done, pending = await asyncio.wait(
                {ended, closed}, timeout=self.settings.max_call_s,
                return_when=asyncio.FIRST_COMPLETED,
            )
            for task in pending:
                task.cancel()
            if closed in done and not self._end.is_set():
                log.warning("the conversation dropped on the provider side")
                name = self.provider.last_provider
                if name:
                    self.provider.penalise(name)
        except AllProvidersFailed as exc:
            log.error("no provider could open the conversation: %s", exc)
        finally:
            if session is not None:
                await session.aclose()
            self.audio.flush_output()
            self.leds.idle()
            self._set_state("idle")
            await self.provider.prefetch()

    def _set_state(self, state: str) -> None:
        self.state = state
        self.bus.publish("call", state=state)

    def status(self) -> dict[str, Any]:
        return {
            "state": self.state,
            "audio": self.audio_ok,
            "levels": {"in": round(self.audio.level_in), "out": round(self.audio.level_out)},
            "provider": self.provider.status(),
            "link": self.link.connected,
            "actions": self.actions.describe(),
            "light": self.leds.current,
            "screen": self.display.lines,
            "transcript": self.transcript if self.settings.store_transcripts else None,
        }
