"""A tiny in-process event bus.

Peripherals, the status page and the reactor learn what happens by
subscribing here, never by calling into the conversation. That keeps a slow
printer or a broken LCD from ever touching the audio path.
"""

from __future__ import annotations

import logging
from collections import defaultdict
from collections.abc import Callable
from typing import Any

log = logging.getLogger("talking_objects.bus")

Listener = Callable[[str, dict[str, Any]], None]


class Bus:
    def __init__(self) -> None:
        self._listeners: dict[str, list[Listener]] = defaultdict(list)
        self._everything: list[Listener] = []

    def subscribe(self, topic: str | None, listener: Listener) -> None:
        """Listen to one topic, or to every topic with `topic=None`."""
        if topic is None:
            self._everything.append(listener)
        else:
            self._listeners[topic].append(listener)

    def publish(self, topic: str, **payload: Any) -> None:
        for listener in (*self._listeners.get(topic, ()), *self._everything):
            try:
                listener(topic, payload)
            except Exception:
                # A listener that fails must not stop the others, nor the
                # conversation that published the event.
                log.exception("listener failed on %s", topic)
