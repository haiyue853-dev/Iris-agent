"""Context compression: summarize old turns to bound context size."""

from __future__ import annotations

from iris_agent.core.models import Message
from iris_agent.providers.base import ModelProvider

_SUMMARY_PREFIX = "[对话摘要] "
_SUMMARY_PROMPT = (
    "你是对话压缩器。把下面的对话历史总结成一段简洁的中文摘要，"
    "保留关键信息：用户目标、已讨论内容、已做的决策、待办事项、用户偏好。"
    "不要遗漏重要事实。只输出摘要正文，不要任何解释。"
)


class ContextCompressor:
    def __init__(
        self,
        provider: ModelProvider,
        trigger_chars: int = 12000,
        trigger_tokens: int | None = None,
        keep_recent: int = 10,
        max_summary_chars: int = 2000,
        enabled: bool = True,
    ):
        self.provider = provider
        self.trigger_chars = trigger_chars
        self.trigger_tokens = trigger_tokens
        self.keep_recent = keep_recent
        self.max_summary_chars = max_summary_chars
        self.enabled = enabled

    def needs_compression(self, messages: list[Message]) -> bool:
        if not self.enabled:
            return False
        if self.trigger_tokens is not None:
            return self._estimate_tokens(messages) > self.trigger_tokens
        return self._total_chars(messages) > self.trigger_chars

    def compress(self, messages: list[Message]) -> list[Message]:
        if self.keep_recent >= len(messages):
            return messages
        cut = len(messages) - self.keep_recent
        while cut > 0 and messages[cut].role == "tool":
            cut -= 1
        recent = messages[cut:]
        old = messages[:cut]
        if not old:
            return messages
        summary = self._summarize(old)
        if not summary:
            return messages
        summary_message = Message(role="system", content=f"{_SUMMARY_PREFIX}{summary[: self.max_summary_chars]}")
        return [summary_message, *recent]

    def _summarize(self, messages: list[Message]) -> str:
        text = self._serialize(messages)
        try:
            response = self.provider.complete(
                [Message(role="system", content=_SUMMARY_PROMPT), Message(role="user", content=text)],
                [],
            )
            return response.content.strip()
        except Exception:
            return ""

    @staticmethod
    def _total_chars(messages: list[Message]) -> int:
        return sum(len(message.model_content) for message in messages)

    @staticmethod
    def _estimate_tokens(messages: list[Message]) -> int:
        chars = sum(len(message.model_content) for message in messages)
        return max(1, (chars + 3) // 4)

    @staticmethod
    def _serialize(messages: list[Message]) -> str:
        lines: list[str] = []
        for message in messages:
            if message.role == "system" and message.content.startswith(_SUMMARY_PREFIX):
                lines.append(f"[历史摘要] {message.content[len(_SUMMARY_PREFIX):]}")
            elif message.role == "tool":
                lines.append(f"[工具] {message.name or 'unknown'}")
            else:
                lines.append(f"{message.role}: {message.content}")
        return "\n".join(lines)
