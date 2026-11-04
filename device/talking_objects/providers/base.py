"""The contract every voice provider follows.

The rest of the object never knows whether Vidiv or ElevenLabs is behind the
conversation. Switching provider is changing one line in `config.env`.

Transcripts arrive normalised as `(speaker, text)` with speaker `agent` or
`visitor`, whoever produced them.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any, Protocol, runtime_checkable

from ..actions import ActionRegistry

Transcript = Callable[[str, str], None]


@runtime_checkable
class VoiceSession(Protocol):
    async def aclose(self) -> None:
        """End the conversation."""

    async def wait_closed(self) -> None:
        """Return when the conversation is over, whoever ended it."""


@runtime_checkable
class VoiceProvider(Protocol):
    name: str

    async def start(
        self, actions: ActionRegistry, *, on_transcript: Transcript | None = None
    ) -> VoiceSession:
        """Mint a fresh credential and open a conversation.

        Called on every trigger. Credentials and sessions are never reused
        between conversations.
        """

    async def prefetch(self) -> None:
        """Optionally prepare a credential while the object is idle."""

    def set_context(self, metadata: dict[str, Any]) -> None:
        """Optionally pass context (mood, place, language) to the next session."""
