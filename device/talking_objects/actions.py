"""One door from software to hardware.

Three callers use it: the agent (by LiveKit RPC, ElevenLabs client tools or
the MCP relay), a reactor rule and, if you add one, a button on a web page.
Sharing one door means one place to validate, one place to limit and one
place to log who asked for what.

Budgets are per action. Lights are free and can blink as much as they like;
a thermal printer uses paper nobody will refill in the middle of a fair, so
it gets a cap per call and per day.

Nothing here can break a conversation: handlers run in the background and
their exceptions are logged and kept here.
"""

from __future__ import annotations

import asyncio
import datetime as _dt
import logging
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Any

log = logging.getLogger("talking_objects.actions")

Handler = Callable[[dict[str, Any]], Awaitable[None]]
Validator = Callable[[dict[str, Any]], dict[str, Any]]


class BudgetExceeded(RuntimeError):
    """The action is valid, but its budget is used up."""


@dataclass
class Budget:
    per_call: int | None = None
    per_day: int | None = None
    cooldown_s: float = 0.0


@dataclass
class Action:
    name: str
    handler: Handler
    description: str = ""
    schema: dict[str, Any] | None = None
    validate: Validator | None = None
    budget: Budget = field(default_factory=Budget)
    used_call: int = 0
    used_day: int = 0
    day: str = ""
    last: float = -1e9


def _today() -> str:
    return _dt.date.today().isoformat()


class ActionRegistry:
    def __init__(
        self,
        bus=None,
        clock: Callable[[], float] = time.monotonic,
        day: Callable[[], str] = _today,
    ) -> None:
        self._actions: dict[str, Action] = {}
        self._bus = bus
        self._clock = clock
        self._day = day
        self._tasks: set[asyncio.Task] = set()

    def register(
        self,
        name: str,
        handler: Handler,
        *,
        description: str = "",
        schema: dict[str, Any] | None = None,
        validate: Validator | None = None,
        budget: Budget | None = None,
    ) -> None:
        """`description` and `schema` (JSON Schema) are what an agent sees
        through MCP: write the description as a cue for WHEN to use it."""
        self._actions[name] = Action(
            name=name,
            handler=handler,
            description=description,
            schema=schema,
            validate=validate,
            budget=budget or Budget(),
            day=self._day(),
        )

    def names(self) -> list[str]:
        return sorted(self._actions)

    def describe(self) -> list[dict[str, Any]]:
        return [
            {
                "name": a.name,
                "description": a.description,
                "input_schema": a.schema or {"type": "object", "properties": {}},
                "used_call": a.used_call,
                "per_call": a.budget.per_call,
                "used_day": a.used_day,
                "per_day": a.budget.per_day,
            }
            for a in sorted(self._actions.values(), key=lambda x: x.name)
        ]

    def new_call(self) -> None:
        """A new conversation refills the per-call budget. The daily one stays."""
        for action in self._actions.values():
            action.used_call = 0

    def fire(self, name: str, args: dict[str, Any], *, source: str) -> str:
        """Validate, check the budget and run in the background. Returns an ack.

        It does not wait for the hardware: the agent gets an answer at once
        and keeps talking while the printer does its thing. Must be called
        from the event loop thread.
        """
        action = self._actions.get(name)
        if action is None:
            raise KeyError(name)
        if action.validate is not None:
            args = action.validate(args)
        self._check_budget(action)

        action.used_call += 1
        action.used_day += 1
        action.last = self._clock()

        task = asyncio.create_task(self._run(action, args))
        # asyncio keeps only weak references to tasks.
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)

        if self._bus is not None:
            self._bus.publish("action", name=name, source=source, args=args)
        return "ok"

    def _check_budget(self, action: Action) -> None:
        today = self._day()
        if action.day != today:
            action.day = today
            action.used_day = 0
        b = action.budget
        if b.cooldown_s and self._clock() - action.last < b.cooldown_s:
            raise BudgetExceeded(f"{action.name}: cooling down")
        if b.per_call is not None and action.used_call >= b.per_call:
            raise BudgetExceeded(f"{action.name}: per-call budget used up")
        if b.per_day is not None and action.used_day >= b.per_day:
            raise BudgetExceeded(f"{action.name}: daily budget used up")

    async def _run(self, action: Action, args: dict[str, Any]) -> None:
        try:
            log.info("action %s %s", action.name, args or "")
            await action.handler(args)
        except Exception as exc:
            log.exception("action %s failed", action.name)
            if self._bus is not None:
                self._bus.publish("device", name=action.name, ok=False, error=str(exc))

    async def drain(self) -> None:
        """Wait for the actions in flight. Useful in tests and on shutdown."""
        if self._tasks:
            await asyncio.gather(*list(self._tasks), return_exceptions=True)
