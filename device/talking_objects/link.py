"""Outbound tunnel from the device to the Cloudflare Worker.

The device usually sits behind the NAT of a venue: nobody on the internet can
reach it. So the direction is reversed. The device opens the connection to
the Worker and keeps it alive; when an agent calls an MCP tool, the order
comes down this same socket. No open ports, no dynamic DNS, no own domain.

Protocol (JSON text frames):

    device -> worker   {"type": "hello", "device": "...", "actions": [...]}
    worker -> device   {"type": "action", "id": "...", "name": "...", "args": {...}}
    device -> worker   {"type": "result", "id": "...", "ok": true|false, "error": "..."}
    worker -> device   {"type": "context", "data": {...}}     # e.g. a mood
    device -> worker   {"type": "event", "topic": "...", ...}  # optional status

It reconnects on its own with growing backoff: venue Wi-Fi drops, and the
object has to come back without anyone restarting it.
"""

from __future__ import annotations

import asyncio
import json
import logging
from collections.abc import Callable
from typing import Any

from .actions import ActionRegistry, BudgetExceeded

log = logging.getLogger("talking_objects.link")

BACKOFF_START_S = 1.0
BACKOFF_MAX_S = 30.0
PING_S = 30


class Link:
    def __init__(
        self,
        url: str,
        actions: ActionRegistry,
        *,
        device_id: str = "object",
        on_context: Callable[[dict[str, Any]], None] | None = None,
        connect=None,
    ) -> None:
        self.url = url
        self.actions = actions
        self.device_id = device_id
        self.on_context = on_context
        self.connected = False
        self._connect = connect
        self._ws = None
        self._task: asyncio.Task | None = None

    def start(self) -> None:
        if not self.url:
            log.warning("no LINK_URL: MCP tools will not reach this device")
            return
        self._task = asyncio.create_task(self._run())

    def stop(self) -> None:
        if self._task is not None:
            self._task.cancel()
            self._task = None

    async def send(self, message: dict[str, Any]) -> None:
        if self._ws is not None:
            try:
                await self._ws.send(json.dumps(message))
            except Exception:
                log.debug("could not send over the link", exc_info=True)

    def _connector(self):
        if self._connect is not None:
            return self._connect
        import websockets

        return lambda url: websockets.connect(url, ping_interval=PING_S, max_size=2**20)

    async def _run(self) -> None:
        backoff = BACKOFF_START_S
        while True:
            try:
                async with self._connector()(self.url) as ws:
                    self._ws = ws
                    self.connected = True
                    backoff = BACKOFF_START_S
                    log.info("link up")
                    await self.send({"type": "hello", "device": self.device_id,
                                     "actions": self.actions.describe()})
                    async for raw in ws:
                        await self.handle(raw)
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                log.warning("link down (%s); retrying in %.0f s", exc, backoff)
            finally:
                self._ws = None
                self.connected = False
            await asyncio.sleep(backoff)
            backoff = min(backoff * 2, BACKOFF_MAX_S)

    async def handle(self, raw: str | bytes) -> None:
        try:
            message = json.loads(raw)
        except (TypeError, ValueError):
            log.warning("ignoring a frame that is not JSON")
            return
        kind = message.get("type")
        if kind == "action":
            result: dict[str, Any] = {"type": "result", "id": message.get("id"), "ok": True}
            try:
                self.actions.fire(str(message.get("name")), message.get("args") or {},
                                  source="mcp")
            except KeyError:
                result.update(ok=False, error=f"unknown action {message.get('name')!r}")
            except (BudgetExceeded, ValueError) as exc:
                result.update(ok=False, error=str(exc))
            await self.send(result)
        elif kind == "context" and self.on_context is not None:
            self.on_context(dict(message.get("data") or {}))
