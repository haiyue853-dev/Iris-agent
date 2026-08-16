"""Multi-platform gateway abstractions.

A "platform adapter" turns an external chat platform (QQ via OneBot, WeCom,
etc.) into inbound text messages that the agent answers.  The adapter is
responsible for both parsing inbound events and relaying the reply back to the
platform; :class:`GatewayService` owns the shared session mapping and the
blocking agent call.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(slots=True)
class InboundMessage:
    """A normalised inbound chat message from any platform."""

    platform: str
    user_id: str
    text: str
    raw: dict = field(default_factory=dict)
