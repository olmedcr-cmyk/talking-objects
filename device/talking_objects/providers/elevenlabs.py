"""ElevenLabs provider: the native Python SDK, no browser.

Per conversation:

    GET /v1/convai/conversation/get-signed-url?agent_id=…   ->  signed wss:// URL
    Conversation(..., audio_interface=DeviceAudioInterface(device))
    register each action as a ClientTool

The API key lives only on the device and is only used here, to mint the
signed URL. The SDK works at 16 kHz and the card at 48 kHz, so resampling
lives at this border.

Pinned against elevenlabs==2.66.0 (see requirements.txt): the
`callback_end_session` wiring is what tells the object a dropped websocket
ended the conversation. Re-check it before upgrading the SDK.
"""

from __future__ import annotations

import asyncio
import json
import logging
import threading
import urllib.parse
import urllib.request
from collections.abc import Callable
from typing import Any

from ..actions import ActionRegistry, BudgetExceeded
from ..audio.device import AudioDevice
from ..audio.dsp import Downsampler48to16, Upsampler16to48
from ..config import ElevenLabsConfig

log = logging.getLogger("talking_objects.elevenlabs")

SIGNED_URL_ENDPOINT = "https://api.elevenlabs.io/v1/convai/conversation/get-signed-url"
TIMEOUT_S = 10
# The SDK's reference interface sends the mic in 4000-frame chunks at 16 kHz
# (250 ms). We capture every 20 ms, so we group up to that size first.
CHUNK_BYTES = 4000 * 2


def fetch_signed_url(cfg: ElevenLabsConfig) -> str:
    """Mint the signed URL. Blocking: call it inside an executor."""
    if not cfg.ready:
        raise RuntimeError("ELEVENLABS_AGENT_ID / ELEVENLABS_API_KEY are not set")
    query = urllib.parse.urlencode({"agent_id": cfg.agent_id})
    req = urllib.request.Request(
        f"{SIGNED_URL_ENDPOINT}?{query}", headers={"xi-api-key": cfg.api_key}
    )
    with urllib.request.urlopen(req, timeout=TIMEOUT_S) as resp:
        data = json.loads(resp.read().decode("utf-8"))
    url = data.get("signed_url")
    if not url:
        raise RuntimeError("ElevenLabs answered without signed_url")
    return url


def _use_url_once(conv: Any, url: str) -> None:
    """Make `start_session` use the URL we already minted instead of asking
    for another one: that saves a full HTTPS round trip after the trigger.
    Patched on the instance, so it does not depend on how the class is built."""
    original = getattr(conv, "_get_signed_url", None)
    pending = [url]

    def once() -> Any:
        if pending:
            return pending.pop()
        return original() if original is not None else None

    conv._get_signed_url = once


class DeviceAudioInterface:
    """Bridge between the SDK (threads and callbacks) and our device (asyncio)."""

    def __init__(self, device: AudioDevice) -> None:
        self._device = device
        self._down = Downsampler48to16()
        self._up = Upsampler16to48()
        self._thread: threading.Thread | None = None
        self._running = threading.Event()

    def start(self, input_callback: Callable[[bytes], None]) -> None:
        self._running.set()
        self._thread = threading.Thread(
            target=self._pump, args=(input_callback,), name="11labs-mic", daemon=True
        )
        self._thread.start()

    def _pump(self, input_callback: Callable[[bytes], None]) -> None:
        loop = self._device.loop
        pending = bytearray()
        while self._running.is_set():
            try:
                pcm48 = asyncio.run_coroutine_threadsafe(self._device.capture(), loop).result(2)
            except Exception:
                return
            pending.extend(self._down.process(pcm48))
            if len(pending) < CHUNK_BYTES:
                continue
            chunk, pending = bytes(pending[:CHUNK_BYTES]), bytearray(pending[CHUNK_BYTES:])
            try:
                input_callback(chunk)
            except Exception:
                if self._running.is_set():
                    log.warning("sending microphone audio failed; stopping", exc_info=True)
                self._running.clear()
                return

    def stop(self) -> None:
        # The SDK may call this from inside our own pump thread when the
        # socket closes; joining the current thread would raise.
        self._running.clear()
        thread, self._thread = self._thread, None
        if thread is not None and thread is not threading.current_thread():
            thread.join(timeout=2)

    def output(self, audio: bytes) -> None:
        self._device.play(self._up.process(audio))

    def interrupt(self) -> None:
        self._device.flush_output()


class ElevenLabsSession:
    def __init__(self, conversation, iface: DeviceAudioInterface) -> None:
        self._conv = conversation
        self._iface = iface
        self._closed = asyncio.Event()

    def mark_closed(self) -> None:
        self._closed.set()

    async def aclose(self) -> None:
        loop = asyncio.get_running_loop()
        try:
            await loop.run_in_executor(None, self._conv.end_session)
        except Exception:
            log.exception("ending the ElevenLabs session")
        self._iface.stop()
        self._closed.set()

    async def wait_closed(self) -> None:
        await self._closed.wait()


class ElevenLabsProvider:
    name = "elevenlabs"

    def __init__(self, cfg: ElevenLabsConfig, audio: AudioDevice) -> None:
        self.cfg = cfg
        self.audio = audio
        self.on_transcript = None
        self._dynamic: dict[str, Any] = {}

    def set_context(self, metadata: dict[str, Any]) -> None:
        """Context reaches the agent as dynamic variables ({{name}} in its prompt)."""
        self._dynamic = {k: str(v) for k, v in (metadata or {}).items()}

    async def prefetch(self) -> None:
        return None

    async def start(self, actions: ActionRegistry, *, on_transcript=None) -> ElevenLabsSession:
        from elevenlabs.client import ElevenLabs
        from elevenlabs.conversational_ai.conversation import (
            AudioInterface,
            ClientTools,
            Conversation,
            ConversationInitiationData,
        )

        if on_transcript is not None:
            self.on_transcript = on_transcript
        loop = asyncio.get_running_loop()
        # Fail here, before opening anything, if the credentials are wrong.
        url = await loop.run_in_executor(None, fetch_signed_url, self.cfg)

        iface = type("Iface", (DeviceAudioInterface, AudioInterface), {})(self.audio)
        tools = ClientTools()
        for name in actions.names():
            tools.register(name, self._client_tool(actions, name, loop), is_async=False)

        session: ElevenLabsSession | None = None

        def ended(*_: Any) -> None:
            # Called from the SDK's own thread, whoever ended the conversation.
            if session is not None:
                loop.call_soon_threadsafe(session.mark_closed)

        conv = Conversation(
            ElevenLabs(api_key=self.cfg.api_key),
            self.cfg.agent_id,
            requires_auth=True,
            config=ConversationInitiationData(dynamic_variables=self._dynamic),
            audio_interface=iface,
            client_tools=tools,
            callback_agent_response=self._say("agent", loop),
            callback_user_transcript=self._say("visitor", loop),
            callback_end_session=ended,
        )
        _use_url_once(conv, url)
        session = ElevenLabsSession(conv, iface)
        await loop.run_in_executor(None, conv.start_session)
        log.info("ElevenLabs conversation open")
        return session

    def _say(self, speaker: str, loop):
        def callback(text: str) -> None:
            if self.on_transcript is not None and text:
                loop.call_soon_threadsafe(self.on_transcript, speaker, text)
        return callback

    @staticmethod
    def _client_tool(actions: ActionRegistry, name: str, loop):
        """ClientTools run sync handlers in the SDK's own thread pool, with no
        running event loop. `actions.fire()` needs one, so it is scheduled on
        ours and the result awaited here."""

        def handler(params: dict[str, Any]) -> str:
            async def fire() -> None:
                actions.fire(name, params or {}, source="agent")

            try:
                asyncio.run_coroutine_threadsafe(fire(), loop).result(timeout=5)
            except BudgetExceeded as exc:
                return json.dumps({"ok": False, "error": str(exc)})
            except Exception as exc:
                log.warning("rejected %s: %s", name, exc)
                return json.dumps({"ok": False, "error": str(exc)})
            return json.dumps({"ok": True})

        return handler
