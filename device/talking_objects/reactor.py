"""Text in, gestures out: the object reacts to what it hears.

Both providers already send the conversation as text. The reactor reads it
and fires actions from `rules.toml`, so lights and screens follow the
conversation without the agent spending a turn deciding a gesture, without a
round trip through MCP and without adding latency to its answers.

The match is deliberately crude. The object does not need to understand: it
only needs to look alive at the moments that matter. The FIRST rule that
matches wins, so order matters.
"""

from __future__ import annotations

import logging
import re
import time
import tomllib
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .actions import ActionRegistry, BudgetExceeded

log = logging.getLogger("talking_objects.reactor")

SPEAKERS = ("any", "agent", "visitor")


@dataclass
class Rule:
    name: str
    pattern: re.Pattern[str]
    action: str
    args: dict[str, Any] = field(default_factory=dict)
    speaker: str = "any"
    cooldown_s: float = 0.0
    per_call: int | None = None
    used: int = 0
    last: float = -1e9


def load_rules(path: str | Path) -> list[Rule]:
    p = Path(path)
    if not p.is_file():
        log.warning("no rules file at %s; the reactor stays quiet", p)
        return []
    data = tomllib.loads(p.read_text(encoding="utf-8"))
    rules = []
    for raw in data.get("rule", []):
        speaker = raw.get("speaker", "any")
        if speaker not in SPEAKERS:
            raise ValueError(f"rule {raw.get('name')!r}: unknown speaker {speaker!r}")
        rules.append(
            Rule(
                name=raw["name"],
                pattern=re.compile(raw["pattern"], re.IGNORECASE),
                action=raw["action"],
                args=dict(raw.get("args", {})),
                speaker=speaker,
                cooldown_s=float(raw.get("cooldown_s", 0)),
                per_call=raw.get("per_call"),
            )
        )
    log.info("%d reactor rules loaded", len(rules))
    return rules


class Reactor:
    def __init__(
        self,
        rules: list[Rule],
        actions: ActionRegistry,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self.rules = rules
        self.actions = actions
        self._clock = clock

    def new_call(self) -> None:
        for rule in self.rules:
            rule.used = 0

    def hear(self, speaker: str, text: str) -> str | None:
        """Feed one piece of transcript. Returns the rule that fired, if any."""
        now = self._clock()
        for rule in self.rules:
            if rule.speaker != "any" and rule.speaker != speaker:
                continue
            if not rule.pattern.search(text):
                continue
            # First match wins, even when it is resting: a resting rule
            # should not hand its moment to a weaker one further down.
            if now - rule.last < rule.cooldown_s:
                return None
            if rule.per_call is not None and rule.used >= rule.per_call:
                return None
            try:
                self.actions.fire(rule.action, dict(rule.args), source="reactor")
            except BudgetExceeded:
                return None
            except KeyError:
                log.warning("rule %s points to unknown action %s", rule.name, rule.action)
                return None
            rule.used += 1
            rule.last = now
            return rule.name
        return None
