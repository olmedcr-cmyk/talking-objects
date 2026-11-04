import asyncio

import numpy as np

from talking_objects import config
from talking_objects.app import App
from talking_objects.audio.device import AudioDevice, OutputRing
from talking_objects.audio.dsp import Downsampler48to16, Ducker, Upsampler16to48, rms
from talking_objects.providers.vidiv import VidivProvider


def tone(n, freq=440, rate=48000, amp=8000):
    t = np.arange(n) / rate
    return (amp * np.sin(2 * np.pi * freq * t)).astype(np.int16).tobytes()


def test_resamplers_keep_length_and_energy():
    down, up = Downsampler48to16(), Upsampler16to48()
    pcm = tone(960)
    low = down.process(pcm)
    assert len(low) == len(pcm) // 3
    back = up.process(low)
    assert len(back) == len(pcm)
    assert rms(back) > 0.5 * rms(pcm)


def test_ducker_only_ducks_while_speaker_plays():
    d = Ducker(12)
    pcm = tone(960)
    assert d.process(pcm, far_rms=0) == pcm
    assert rms(d.process(pcm, far_rms=5000)) < 0.3 * rms(pcm)


def test_output_ring_pads_with_silence_and_caps():
    ring = OutputRing(block_bytes=4, max_seconds=1, bytes_per_second=8)
    assert ring.pop_block() == bytes(4)
    ring.push(b"\x01" * 20)
    assert len(ring) == 8
    ring.clear()
    assert len(ring) == 0


def test_vidiv_keeps_only_new_visitor_text():
    p = VidivProvider(config.VidivConfig("slug", "wss://x"), audio=None)
    assert p.only_new("visitor", "Hello?") == "Hello?"
    assert p.only_new("visitor", "Hello?") == ""
    assert p.only_new("visitor", "Hello? Can you hear me") == " Can you hear me"
    assert p.only_new("agent", "Yes") == "Yes"


class Session:
    def __init__(self):
        self.closed = asyncio.Event()
        self.aclosed = False

    async def aclose(self):
        self.aclosed = True
        self.closed.set()

    async def wait_closed(self):
        await self.closed.wait()


class Provider:
    def __init__(self):
        self.session = Session()
        self.heard = None

    def order(self):
        return ["fake"]

    def status(self):
        return {"provider": "fake"}

    def set_context(self, _):
        pass

    async def prefetch(self):
        pass

    def penalise(self, _):
        pass

    last_provider = "fake"

    async def start(self, actions, *, on_transcript=None):
        self.heard = on_transcript
        return self.session


async def test_a_whole_conversation_with_null_audio(monkeypatch, tmp_path):
    monkeypatch.setenv("FAKE_AUDIO", "1")
    monkeypatch.setenv("TRIGGER_MODE", "keyboard")
    monkeypatch.setenv("RULES_PATH", "rules.example.toml")
    monkeypatch.setenv("LINK_URL", "")
    settings = config.load(tmp_path / "none.env")
    provider = Provider()
    app = App(settings, provider=provider, audio=AudioDevice(settings.audio, null=True))
    app.audio.start()
    app.audio_ok = True
    try:
        app.on_start()
        await asyncio.sleep(0.05)
        assert app.state == "talking"
        provider.heard("agent", "Hola, bienvenida")
        await app.actions.drain()
        light = next(a for a in app.status()["actions"] if a["name"] == "light")
        assert light["used_call"] == 1  # the "greeting" rule fired
        assert app.status()["transcript"] is None  # not stored by default
        app.on_end()
        await asyncio.sleep(0.05)
        assert app.state == "idle" and provider.session.aclosed
    finally:
        app.audio.stop()


async def test_ringback_plays_until_cancelled():
    from talking_objects.audio.tones import ringback, tone

    played = []
    task = asyncio.create_task(ringback(played.append))
    await asyncio.sleep(0.01)
    task.cancel()
    assert len(played) == 1 and len(played[0]) == len(tone(1.0))
    assert rms(played[0]) > 1000
