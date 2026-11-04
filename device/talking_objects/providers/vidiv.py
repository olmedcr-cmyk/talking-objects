"""Vidiv provider: Vidiv mints the token, LiveKit carries the audio.

Per conversation:

    POST {VIDIV_API_BASE}/api/v2/agents/{slug}/token   ->  short-lived JWT
    Room.connect(LIVEKIT_URL, JWT)
    publish the microphone  +  subscribe to the agent's audio
    register each action as a LiveKit RPC method

Vidiv's rule, kept here: a fresh token for every conversation and never
reuse the previous session. That is why `start()` builds everything anew.
Ported from TeleTUP, where it runs in a public phone booth.
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
import urllib.error
import urllib.request
from typing import Any

from ..actions import ActionRegistry, BudgetExceeded
from ..audio.device import AudioDevice
from ..config import VidivConfig

log = logging.getLogger("talking_objects.vidiv")

TOKEN_TIMEOUT_S = 15
# After this much silence, an identical phrase counts as said again.
TRANSCRIPT_MEMORY_S = 8.0


class VidivTokenError(RuntimeError):
    """The token could not be minted."""


def fetch_token(cfg: VidivConfig, metadata: dict[str, Any]) -> str:
    """Ask Vidiv for a JWT. Blocking: call it inside an executor."""
    body = json.dumps(
        {
            "name": "Visitor",
            "language": cfg.language,
            "metadata": {"interface": "talking-objects", **metadata},
        }
    ).encode("utf-8")
    req = urllib.request.Request(
        cfg.token_url, data=body, headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=TOKEN_TIMEOUT_S) as resp:
            payload = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", "replace")[:400]
        raise VidivTokenError(f"HTTP {exc.code} from Vidiv: {detail}") from exc
    except Exception as exc:
        raise VidivTokenError(f"asking Vidiv for a token failed: {exc}") from exc

    # Documented shape: {"data": {"token": "..."}}. A flat shape is accepted
    # too, because the contract can vary between accounts.
    token = (payload.get("data") or {}).get("token") or payload.get("token")
    if not token:
        raise VidivTokenError("Vidiv answered without a token")
    return token


class VidivSession:
    def __init__(self, room) -> None:
        self._room = room
        self._tasks: list[asyncio.Task] = []
        self._closed = asyncio.Event()
        room.on("disconnected", lambda *_: self._closed.set())

    def track(self, task: asyncio.Task) -> None:
        self._tasks.append(task)

    async def aclose(self) -> None:
        for task in self._tasks:
            task.cancel()
        self._tasks.clear()
        try:
            await self._room.disconnect()
        except Exception:
            log.exception("disconnecting from LiveKit")
        self._closed.set()

    async def wait_closed(self) -> None:
        await self._closed.wait()


class VidivProvider:
    name = "vidiv"

    def __init__(self, cfg: VidivConfig, audio: AudioDevice) -> None:
        self.cfg = cfg
        self.audio = audio
        self.on_transcript = None
        self._context: dict[str, Any] = {}
        self._token: str | None = None
        self._last_text: dict[str, tuple[str, float]] = {}

    # -- credentials --------------------------------------------------------
    def set_context(self, metadata: dict[str, Any]) -> None:
        """Context travels in the token body, so a new context drops a
        prefetched token: it was minted with the old one baked in."""
        new = dict(metadata or {})
        if self._token is not None and new != self._context:
            self._token = None
        self._context = new

    async def prefetch(self) -> None:
        """Keep a token ready. Saves about a second when someone picks up."""
        if self._token is not None:
            return
        try:
            self._token = await self._mint(self._context)
        except Exception:
            log.warning("could not prefetch a Vidiv token; will ask on trigger")

    async def _mint(self, metadata: dict[str, Any]) -> str:
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(None, fetch_token, self.cfg, metadata)

    # -- conversation -------------------------------------------------------
    async def start(self, actions: ActionRegistry, *, on_transcript=None) -> VidivSession:
        from livekit import rtc  # imported here so tests and Macs need no LiveKit

        if on_transcript is not None:
            self.on_transcript = on_transcript
        token, self._token = self._token, None
        if token is None:
            token = await self._mint(self._context)

        self._last_text.clear()
        room = rtc.Room()
        session = VidivSession(room)

        def on_track(track, *_):
            if track.kind == rtc.TrackKind.KIND_AUDIO:
                session.track(asyncio.create_task(self._play(rtc, track)))

        room.on("track_subscribed", on_track)
        await room.connect(self.cfg.livekit_url, token)
        log.info("connected to room %s", room.name)

        self._listen_transcription(room, session)
        self._register_tools(rtc, room, actions)
        await self._publish_microphone(rtc, room, session)
        return session

    def _listen_transcription(self, room, session: VidivSession) -> None:
        """LiveKit already sends the live transcription as a text stream."""
        if self.on_transcript is None:
            return
        me = room.local_participant.identity

        async def read(reader, identity: str) -> None:
            speaker = "visitor" if identity == me else "agent"
            try:
                async for chunk in reader:
                    new = self.only_new(speaker, chunk)
                    if new:
                        self.on_transcript(speaker, new)
            except Exception:
                log.exception("reading the transcription")

        def handler(reader, identity: str) -> None:
            # LiveKit calls this synchronously and discards the return value:
            # registering a coroutine here would never run. Schedule a task.
            session.track(asyncio.create_task(read(reader, identity)))

        room.register_text_stream_handler("lk.transcription", handler)

    def only_new(self, speaker: str, chunk: str) -> str:
        """Return what has not been emitted yet for this speaker, or "".

        The agent arrives as deltas. The visitor arrives as CUMULATIVE
        snapshots: the recogniser resends the whole sentence each time it
        refines it. Without this, history is unreadable and the reactor
        hears the same word dozens of times.
        """
        if speaker != "visitor":
            return chunk
        now = time.monotonic()
        previous, when = self._last_text.get(speaker, ("", 0.0))
        if now - when > TRANSCRIPT_MEMORY_S:
            previous = ""
        self._last_text[speaker] = (chunk, now)
        if chunk == previous:
            return ""
        if previous and chunk.startswith(previous):
            return chunk[len(previous):]
        return chunk

    def _register_tools(self, rtc, room, actions: ActionRegistry) -> None:
        for name in actions.names():

            async def handler(data, _name: str = name) -> str:
                try:
                    payload = json.loads(data.payload) if data.payload else {}
                    actions.fire(_name, payload, source="agent")
                except BudgetExceeded as exc:
                    return json.dumps({"ok": False, "error": str(exc)})
                except Exception as exc:
                    log.warning("rejected %s: %s", _name, exc)
                    return json.dumps({"ok": False, "error": str(exc)})
                return json.dumps({"ok": True})

            # In the Python SDK, RPC lives on LocalParticipant (the JS SDK
            # puts it on Room, which is what most guides show).
            room.local_participant.register_rpc_method(name, handler)
        log.info("RPC tools: %s", ", ".join(actions.names()) or "(none)")

    async def _publish_microphone(self, rtc, room, session: VidivSession) -> None:
        cfg = self.audio.cfg
        source = rtc.AudioSource(cfg.sample_rate, cfg.channels)
        track = rtc.LocalAudioTrack.create_audio_track("mic", source)
        options = rtc.TrackPublishOptions(source=rtc.TrackSource.SOURCE_MICROPHONE)
        await room.local_participant.publish_track(track, options)

        async def pump() -> None:
            while True:
                pcm = await self.audio.capture()
                await source.capture_frame(
                    rtc.AudioFrame(
                        data=pcm,
                        sample_rate=cfg.sample_rate,
                        num_channels=cfg.channels,
                        samples_per_channel=len(pcm) // (2 * cfg.channels),
                    )
                )

        session.track(asyncio.create_task(pump()))

    async def _play(self, rtc, track) -> None:
        cfg = self.audio.cfg
        stream = rtc.AudioStream(track, sample_rate=cfg.sample_rate, num_channels=cfg.channels)
        try:
            async for event in stream:
                self.audio.play(bytes(event.frame.data))
        finally:
            await stream.aclose()
