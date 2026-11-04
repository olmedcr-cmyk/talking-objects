import asyncio
import json
import re

import pytest

from talking_objects.actions import ActionRegistry, Budget, BudgetExceeded
from talking_objects.bus import Bus
from talking_objects.config import FailoverConfig, load, parse_color
from talking_objects.devices.display import layout, validate_message
from talking_objects.devices.leds import validate_light
from talking_objects.link import Link
from talking_objects.providers.failover import AllProvidersFailed, FailoverProvider
from talking_objects.reactor import Reactor, Rule, load_rules


class Clock:
    def __init__(self) -> None:
        self.t = 1000.0

    def __call__(self) -> float:
        return self.t


def registry(clock=None):
    calls = []

    async def handler(args):
        calls.append(args)

    reg = ActionRegistry(bus=Bus(), clock=clock or Clock())
    reg.register("light", handler, budget=Budget(per_call=2, cooldown_s=5))
    return reg, calls


# -- actions ---------------------------------------------------------------
async def test_fire_runs_in_background_and_respects_budget():
    clock = Clock()
    reg, calls = registry(clock)
    assert reg.fire("light", {"color": "blue"}, source="test") == "ok"
    with pytest.raises(BudgetExceeded):
        reg.fire("light", {}, source="test")  # cooling down
    clock.t += 10
    reg.fire("light", {}, source="test")
    clock.t += 10
    with pytest.raises(BudgetExceeded):
        reg.fire("light", {}, source="test")  # per-call budget used up
    reg.new_call()
    reg.fire("light", {}, source="test")
    await reg.drain()
    assert len(calls) == 3


async def test_unknown_action_raises_keyerror():
    reg, _ = registry()
    with pytest.raises(KeyError):
        reg.fire("nope", {}, source="test")


async def test_handler_failure_is_reported_not_raised():
    bus = Bus()
    seen = []
    bus.subscribe("device", lambda t, p: seen.append(p))
    reg = ActionRegistry(bus=bus)

    async def broken(_):
        raise RuntimeError("no paper")

    reg.register("print", broken)
    reg.fire("print", {}, source="test")
    await reg.drain()
    assert seen and seen[0]["ok"] is False


# -- reactor ---------------------------------------------------------------
async def test_reactor_first_match_wins_and_limits(tmp_path):
    clock = Clock()
    reg, calls = registry(clock)
    rules = [
        Rule("memory", re.compile(r"\bmemor", re.I), "light", {"color": "blue"},
             speaker="any", cooldown_s=20, per_call=1),
    ]
    reactor = Reactor(rules, reg, clock=clock)
    assert reactor.hear("visitor", "I lost my memory") == "memory"
    clock.t += 30
    assert reactor.hear("visitor", "memory again") is None  # per_call reached
    assert reactor.hear("agent", "nothing here") is None
    await reg.drain()
    assert calls == [{"color": "blue"}]


def test_example_rules_load():
    rules = load_rules("rules.example.toml")
    assert [r.name for r in rules][:2] == ["greeting", "memory"]


# -- failover --------------------------------------------------------------
class FakeSession:
    async def aclose(self):
        pass

    async def wait_closed(self):
        await asyncio.Event().wait()


class FakeProvider:
    def __init__(self, name, ok=True):
        self.name, self.ok, self.calls = name, ok, 0

    async def start(self, actions, *, on_transcript=None):
        self.calls += 1
        if not self.ok:
            raise RuntimeError("down")
        return FakeSession()


async def test_failover_falls_back_and_breaker_demotes():
    clock = Clock()
    vidiv, eleven = FakeProvider("vidiv", ok=False), FakeProvider("elevenlabs")
    fp = FailoverProvider({"vidiv": vidiv, "elevenlabs": eleven},
                          FailoverConfig(breaker_failures=2, breaker_cooldown_s=60), clock=clock)
    reg, _ = registry()
    await fp.start(reg)
    assert fp.last_provider == "elevenlabs" and fp.last_fallback
    await fp.start(reg)
    assert fp.order() == ["elevenlabs", "vidiv"]  # vidiv degraded, goes last
    clock.t += 61
    assert fp.order() == ["vidiv", "elevenlabs"]


async def test_failover_all_down():
    fp = FailoverProvider({"vidiv": FakeProvider("vidiv", ok=False)}, FailoverConfig())
    reg, _ = registry()
    with pytest.raises(AllProvidersFailed):
        await fp.start(reg)


# -- link ------------------------------------------------------------------
async def test_link_runs_actions_and_reports():
    reg, calls = registry()
    sent = []
    link = Link("wss://example", reg)

    async def send(message):
        sent.append(message)

    link.send = send
    await link.handle(json.dumps({"type": "action", "id": "1", "name": "light", "args": {"a": 1}}))
    await link.handle(json.dumps({"type": "action", "id": "2", "name": "nope"}))
    await link.handle("not json")
    await reg.drain()
    assert sent[0] == {"type": "result", "id": "1", "ok": True}
    assert sent[1]["ok"] is False and "unknown action" in sent[1]["error"]
    assert calls == [{"a": 1}]


async def test_link_passes_context():
    reg, _ = registry()
    got = []
    link = Link("wss://example", reg, on_context=got.append)
    await link.handle(json.dumps({"type": "context", "data": {"mood": "calm"}}))
    assert got == [{"mood": "calm"}]


# -- devices and config ----------------------------------------------------
def test_light_validation():
    assert validate_light({"color": "Blue"}) == {"color": "blue", "effect": "solid", "seconds": 6.0}
    with pytest.raises(ValueError):
        validate_light({"color": "magenta-ish"})


def test_display_layout_strips_accents_and_wraps():
    lines = layout("Te estoy escuchando, corazón")
    assert lines[0] == "TE ESTOY ESCUCHANDO,"
    assert lines[1].startswith("CORAZON")
    assert len(lines) == 4 and all(len(line) == 20 for line in lines)
    with pytest.raises(ValueError):
        validate_message({"text": "  "})


def test_parse_color():
    assert parse_color("40,30,20") == (40, 30, 20)
    assert parse_color("off") is None
    assert parse_color("300,0,0") is None


def test_config_defaults_warn_but_do_not_fail(monkeypatch, tmp_path):
    for var in ("VIDIV_AGENT_SLUG", "LIVEKIT_URL", "ELEVENLABS_AGENT_ID",
                "ELEVENLABS_API_KEY", "LINK_URL", "PROVIDER_MODE"):
        monkeypatch.delenv(var, raising=False)
    env = tmp_path / "config.env"
    env.write_text("PROVIDER_MODE=sideways\nLED_IDLE_COLOR=1,2,3\n")
    s = load(env)
    assert s.failover.mode == "auto"
    assert s.leds.idle_color == (1, 2, 3)
    assert s.store_transcripts is False
    assert any("PROVIDER_MODE" in w for w in s.warnings)
