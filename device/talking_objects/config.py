"""Typed configuration, read from `config.env` and the process environment.

The environment wins over the file, so a systemd override or a one-off
`VAR=… python -m talking_objects` never needs the file to be edited.

A missing optional value never stops the object from starting: under systemd,
refusing to start means dying and restarting every few seconds without ever
bringing up anything a person could use to diagnose it.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

PROVIDER_MODES = ("auto", "vidiv", "elevenlabs")
TRIGGER_MODES = ("gpio", "keyboard", "auto")


def load_env_file(path: str | os.PathLike | None) -> None:
    """Load KEY=VALUE lines into os.environ without overriding what is set."""
    if not path:
        return
    p = Path(path)
    if not p.is_file():
        return
    for raw in p.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        value = value.split(" #", 1)[0].strip().strip('"').strip("'")
        os.environ.setdefault(key.strip(), value)


def _env(name: str, default: str = "") -> str:
    return os.environ.get(name, default).strip()


def _int(name: str, default: int) -> int:
    value = _env(name)
    return int(value) if value else default


def _float(name: str, default: float) -> float:
    value = _env(name)
    return float(value) if value else default


def _bool(name: str, default: bool = False) -> bool:
    value = _env(name).lower()
    if not value:
        return default
    return value in ("1", "true", "yes", "on")


@dataclass(frozen=True)
class VidivConfig:
    """Vidiv mints the token; LiveKit carries the audio."""

    agent_slug: str
    livekit_url: str
    api_base: str = "https://api.vidiv.net"
    language: str = "es"

    @property
    def token_url(self) -> str:
        return f"{self.api_base}/api/v2/agents/{self.agent_slug}/token"

    @property
    def ready(self) -> bool:
        return bool(self.agent_slug and self.livekit_url)


@dataclass(frozen=True)
class ElevenLabsConfig:
    agent_id: str
    api_key: str

    @property
    def ready(self) -> bool:
        return bool(self.agent_id and self.api_key)


@dataclass(frozen=True)
class FailoverConfig:
    mode: str = "auto"
    # Consecutive connection failures before a provider gives up first place.
    breaker_failures: int = 2
    breaker_cooldown_s: int = 300


@dataclass(frozen=True)
class AudioConfig:
    sample_rate: int = 48000
    channels: int = 1
    block_ms: int = 20
    input_device: str | None = None
    output_device: str | None = None
    # How much the microphone drops while the agent speaks, in dB. It is what
    # stops the speaker leaking into the mic and the agent interrupting itself.
    duck_db: float = 12.0

    @property
    def block_frames(self) -> int:
        return self.sample_rate * self.block_ms // 1000

    @property
    def block_bytes(self) -> int:
        return self.block_frames * 2 * self.channels


@dataclass(frozen=True)
class TriggerConfig:
    mode: str = "gpio"
    pin: int = 17
    bounce_ms: int = 300
    invert: bool = False
    auto_pause_s: float = 20.0


@dataclass(frozen=True)
class LedConfig:
    count: int = 60
    brightness: float = 0.35
    idle_color: tuple[int, int, int] | None = None


@dataclass(frozen=True)
class Settings:
    vidiv: VidivConfig
    elevenlabs: ElevenLabsConfig
    failover: FailoverConfig
    audio: AudioConfig
    trigger: TriggerConfig
    leds: LedConfig
    link_url: str = ""
    lcd_address: int | None = None
    rules_path: str = "rules.toml"
    max_call_s: int = 600
    status_port: int = 8081
    # Off by default. Transcripts are personal data; an object in a public
    # space should not keep them unless someone decided so on purpose.
    store_transcripts: bool = False
    fake_audio: bool = False
    warnings: list[str] = field(default_factory=list)


def parse_color(text: str | None) -> tuple[int, int, int] | None:
    """"255,180,90" -> (255, 180, 90). Empty, "off" or malformed -> None."""
    if not text or text.strip().lower() in ("off", "none", "0"):
        return None
    try:
        r, g, b = (int(x) for x in text.replace(";", ",").split(","))
    except ValueError:
        return None
    if not all(0 <= c <= 255 for c in (r, g, b)):
        return None
    return (r, g, b)


def load(env_file: str | os.PathLike | None = "config.env") -> Settings:
    load_env_file(env_file)
    warnings: list[str] = []

    mode = _env("PROVIDER_MODE", "auto").lower()
    if mode not in PROVIDER_MODES:
        warnings.append(f"PROVIDER_MODE={mode!r} is unknown; using 'auto'")
        mode = "auto"

    trigger_mode = _env("TRIGGER_MODE", "gpio").lower()
    if trigger_mode not in TRIGGER_MODES:
        warnings.append(f"TRIGGER_MODE={trigger_mode!r} is unknown; using 'gpio'")
        trigger_mode = "gpio"

    lcd = _env("LCD_ADDRESS")
    settings = Settings(
        vidiv=VidivConfig(
            agent_slug=_env("VIDIV_AGENT_SLUG"),
            livekit_url=_env("LIVEKIT_URL"),
            api_base=_env("VIDIV_API_BASE", "https://api.vidiv.net"),
            language=_env("LANGUAGE", "es"),
        ),
        elevenlabs=ElevenLabsConfig(
            agent_id=_env("ELEVENLABS_AGENT_ID"),
            api_key=_env("ELEVENLABS_API_KEY"),
        ),
        failover=FailoverConfig(
            mode=mode,
            breaker_failures=_int("BREAKER_FAILURES", 2),
            breaker_cooldown_s=_int("BREAKER_COOLDOWN_S", 300),
        ),
        audio=AudioConfig(
            sample_rate=_int("AUDIO_SAMPLE_RATE", 48000),
            channels=_int("AUDIO_CHANNELS", 1),
            block_ms=_int("AUDIO_BLOCK_MS", 20),
            input_device=_env("AUDIO_INPUT_DEVICE") or None,
            output_device=_env("AUDIO_OUTPUT_DEVICE") or None,
            duck_db=_float("MIC_DUCK_DB", 12.0),
        ),
        trigger=TriggerConfig(
            mode=trigger_mode,
            pin=_int("TRIGGER_GPIO", 17),
            bounce_ms=_int("TRIGGER_BOUNCE_MS", 300),
            invert=_bool("TRIGGER_INVERT"),
            auto_pause_s=_float("AUTO_PAUSE_S", 20.0),
        ),
        leds=LedConfig(
            count=_int("LED_COUNT", 60),
            brightness=_float("LED_BRIGHTNESS", 0.35),
            idle_color=parse_color(_env("LED_IDLE_COLOR")),
        ),
        link_url=_env("LINK_URL"),
        lcd_address=int(lcd, 0) if lcd else None,
        rules_path=_env("RULES_PATH", "rules.toml"),
        max_call_s=_int("MAX_CALL_SECONDS", 600),
        status_port=_int("STATUS_PORT", 8081),
        store_transcripts=_bool("STORE_TRANSCRIPTS"),
        fake_audio=_bool("FAKE_AUDIO"),
        warnings=warnings,
    )

    if mode in ("auto", "vidiv") and not settings.vidiv.ready:
        warnings.append("Vidiv is not configured (VIDIV_AGENT_SLUG, LIVEKIT_URL)")
    if mode in ("auto", "elevenlabs") and not settings.elevenlabs.ready:
        warnings.append(
            "ElevenLabs is not configured (ELEVENLABS_AGENT_ID, ELEVENLABS_API_KEY)"
            + ("; running without failover" if mode == "auto" else "")
        )
    if not settings.link_url:
        warnings.append("LINK_URL is empty: MCP tools will not reach this device")
    return settings
