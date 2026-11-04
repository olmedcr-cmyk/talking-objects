"""The thread that owns the sound card. Nobody else touches it.

One thread, one handle and a fixed order, because the blocking PortAudio API
does not tolerate two threads reading and writing the same stream at once:

    near = read()      the microphone sets the clock: blocks until a block is ready
    far  = ring        silence if there is nothing to play, never waits
    write(far)         does not block: the card has just freed a block
    duck(near, far)    the mic drops while the speaker plays
    -> input queue     towards the asyncio loop

Reading before writing is what guarantees there is room when `write` runs.
This is the same design that runs TeleTUP, simplified for the kit.
"""

from __future__ import annotations

import asyncio
import logging
import threading
import time

from ..config import AudioConfig
from . import dsp

log = logging.getLogger("talking_objects.audio")

try:  # pragma: no cover - depends on the host
    import sounddevice as _sd
except Exception as exc:  # PortAudio missing, e.g. a bare Mac
    _sd = None
    _IMPORT_ERROR: Exception | None = exc
else:
    _IMPORT_ERROR = None


class AudioUnavailable(RuntimeError):
    """The sound card could not be opened."""


class OutputRing:
    """What the agent says, waiting to be played. Thread-safe."""

    def __init__(self, block_bytes: int, max_seconds: float, bytes_per_second: int) -> None:
        self.block_bytes = block_bytes
        self.max_bytes = int(max_seconds * bytes_per_second)
        self._buf = bytearray()
        self._lock = threading.Lock()

    def push(self, pcm: bytes) -> None:
        with self._lock:
            self._buf.extend(pcm)
            overflow = len(self._buf) - self.max_bytes
            if overflow > 0:
                del self._buf[:overflow]

    def pop_block(self) -> bytes:
        with self._lock:
            if len(self._buf) < self.block_bytes:
                return dsp.silence(self.block_bytes)
            block = bytes(self._buf[: self.block_bytes])
            del self._buf[: self.block_bytes]
            return block

    def clear(self) -> None:
        with self._lock:
            self._buf.clear()

    def __len__(self) -> int:
        with self._lock:
            return len(self._buf)


class InputQueue:
    """Microphone blocks crossing from the audio thread into asyncio."""

    def __init__(self, loop: asyncio.AbstractEventLoop, maxsize: int = 50) -> None:
        self._loop = loop
        self._q: asyncio.Queue[bytes] = asyncio.Queue(maxsize=maxsize)

    def push_from_thread(self, pcm: bytes) -> None:
        self._loop.call_soon_threadsafe(self._put, pcm)

    def _put(self, pcm: bytes) -> None:
        if self._q.full():
            # Old microphone audio is worthless: drop it rather than lag.
            self._q.get_nowait()
        self._q.put_nowait(pcm)

    async def get(self) -> bytes:
        return await self._q.get()


class _NullStream:
    """Silence at real-time pace, for development without a sound card."""

    def __init__(self, cfg: AudioConfig) -> None:
        self.cfg = cfg
        self._next = time.monotonic()

    def start(self) -> None:
        self._next = time.monotonic()

    def read(self, frames: int):
        self._next += frames / self.cfg.sample_rate
        delay = self._next - time.monotonic()
        if delay > 0:
            time.sleep(delay)
        return dsp.silence(frames * 2 * self.cfg.channels), False

    def write(self, pcm: bytes) -> bool:
        return False

    def stop(self) -> None:
        pass

    def close(self) -> None:
        pass


class AudioDevice:
    def __init__(self, cfg: AudioConfig, *, null: bool = False) -> None:
        self.cfg = cfg
        self.null = null
        self._ring = OutputRing(cfg.block_bytes, 10.0, cfg.sample_rate * 2 * cfg.channels)
        self._ducker = dsp.Ducker(cfg.duck_db)
        self._stream = None
        self._thread: threading.Thread | None = None
        self._running = threading.Event()
        self._loop: asyncio.AbstractEventLoop | None = None
        self._input: InputQueue | None = None
        self.level_in = 0.0
        self.level_out = 0.0

    @property
    def running(self) -> bool:
        return self._running.is_set()

    def start(self) -> None:
        """Open the card and start the owner thread. Call from the event loop."""
        self._loop = asyncio.get_running_loop()
        self._input = InputQueue(self._loop)
        self._stream = self._open_stream()
        self._stream.start()
        self._running.set()
        self._thread = threading.Thread(target=self._run, name="audio-owner", daemon=True)
        self._thread.start()
        log.info("audio running at %d Hz, %d ms blocks%s", self.cfg.sample_rate,
                 self.cfg.block_ms, " (null device)" if self.null else "")

    def _open_stream(self):
        if self.null:
            return _NullStream(self.cfg)
        if _sd is None:
            raise AudioUnavailable(f"sounddevice is not available: {_IMPORT_ERROR}")
        try:
            return _sd.RawStream(
                samplerate=self.cfg.sample_rate,
                channels=self.cfg.channels,
                dtype="int16",
                blocksize=self.cfg.block_frames,
                device=(self.cfg.input_device, self.cfg.output_device),
                latency="low",
            )
        except Exception as exc:
            raise AudioUnavailable(str(exc)) from exc

    def stop(self) -> None:
        self._running.clear()
        if self._thread is not None:
            self._thread.join(timeout=2)
            self._thread = None
        if self._stream is not None:
            try:
                self._stream.stop()
                self._stream.close()
            except Exception:
                log.debug("closing the stream", exc_info=True)
            self._stream = None

    def _run(self) -> None:
        frames = self.cfg.block_frames
        while self._running.is_set():
            try:
                near, _overflow = self._stream.read(frames)
                near = bytes(near)
                far = self._ring.pop_block()
                self._stream.write(far)
                far_rms = dsp.rms(far)
                self.level_out = far_rms
                self.level_in = dsp.rms(near)
                self._input.push_from_thread(self._ducker.process(near, far_rms))
            except Exception:
                log.exception("audio loop error; retrying in 0.5 s")
                time.sleep(0.5)

    # -- API used by the providers ------------------------------------------
    def play(self, pcm: bytes) -> None:
        """Queue agent audio. Safe from any thread."""
        self._ring.push(pcm)

    async def capture(self) -> bytes:
        """Next microphone block, already ducked."""
        if self._input is None:
            raise AudioUnavailable("audio device not started")
        return await self._input.get()

    def flush_output(self) -> None:
        """The visitor interrupted: what was left to play no longer counts."""
        self._ring.clear()

    @property
    def loop(self) -> asyncio.AbstractEventLoop | None:
        return self._loop
