"""Pick a provider, switch when one fails, stop insisting on the one that does not work.

Two failure cases, handled differently:

  - **On connect.** Solved here, while the waiting tones play. The visitor
    is already waiting for an answer and notices nothing.

  - **Mid-conversation.** Not solved here: context does not migrate between
    providers. The app decides whether to reconnect; this module only says
    whether there is an alternative and pushes the failed one to the back.

The circuit breaker exists for the second visitor: without it, they would
pay again for the first visitor's failed attempt, and so would the third.
"""

from __future__ import annotations

import logging
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from ..actions import ActionRegistry
from ..config import FailoverConfig

log = logging.getLogger("talking_objects.failover")

PREFERENCE = ("vidiv", "elevenlabs")


class AllProvidersFailed(RuntimeError):
    """No available provider could open the conversation."""


@dataclass
class _State:
    failures: int = 0
    degraded_until: float = 0.0


@dataclass
class FailoverProvider:
    providers: dict[str, Any]
    cfg: FailoverConfig
    bus: Any = None
    clock: Callable[[], float] = time.monotonic
    name: str = "failover"
    last_provider: str | None = None
    last_fallback: bool = False
    _state: dict[str, _State] = field(default_factory=dict)

    def __post_init__(self) -> None:
        self.mode = self.cfg.mode
        self._state = {n: _State() for n in self.providers}

    def order(self) -> list[str]:
        """Who to ask, in which order, right now."""
        if self.mode != "auto":
            return [self.mode] if self.mode in self.providers else []
        names = [n for n in PREFERENCE if n in self.providers]
        # Degraded providers go last, not out: if the other one fails too,
        # trying is better than leaving the visitor in silence.
        return sorted(names, key=self._degraded)

    def _degraded(self, name: str) -> bool:
        return self._state[name].degraded_until > self.clock()

    def has_alternative(self, exclude: str) -> bool:
        return any(n != exclude for n in self.order())

    def set_context(self, metadata: dict[str, Any]) -> None:
        for provider in self.providers.values():
            setter = getattr(provider, "set_context", None)
            if setter is not None:
                setter(metadata)

    async def prefetch(self) -> None:
        for name in self.order():
            prefetch = getattr(self.providers[name], "prefetch", None)
            if prefetch is None:
                continue
            try:
                await prefetch()
            except Exception:
                log.debug("prefetch failed for %s", name, exc_info=True)

    async def start(self, actions: ActionRegistry, *, on_transcript=None):
        order = self.order()
        if not order:
            raise AllProvidersFailed(f"no provider for mode {self.mode!r}")
        problems = []
        for i, name in enumerate(order):
            try:
                session = await self.providers[name].start(actions, on_transcript=on_transcript)
            except Exception as exc:
                log.warning("%s did not connect: %s", name, exc)
                problems.append(f"{name}: {exc}")
                self._record_failure(name)
                continue
            self._state[name] = _State()
            self.last_provider = name
            self.last_fallback = i > 0
            if self.last_fallback:
                log.info("fell back to %s", name)
            self._publish(name)
            return session
        raise AllProvidersFailed("; ".join(problems))

    def _record_failure(self, name: str) -> None:
        state = self._state[name]
        state.failures += 1
        if state.failures >= self.cfg.breaker_failures:
            state.degraded_until = self.clock() + self.cfg.breaker_cooldown_s
            log.warning("%s degraded after %d failures for %d s",
                        name, state.failures, self.cfg.breaker_cooldown_s)
        self._publish(name, error=True)

    def penalise(self, name: str) -> None:
        """Send to the back of the queue the provider that just dropped mid-call."""
        if name in self._state:
            self._state[name].degraded_until = self.clock() + self.cfg.breaker_cooldown_s

    def status(self) -> dict[str, Any]:
        return {
            "mode": self.mode,
            "provider": self.last_provider,
            "fallback": self.last_fallback,
            "order": self.order(),
            "degraded": [n for n in self.providers if self._degraded(n)],
        }

    def _publish(self, name: str, error: bool = False) -> None:
        if self.bus is not None:
            self.bus.publish("provider", name=name, fallback=self.last_fallback,
                             error=error, mode=self.mode)
