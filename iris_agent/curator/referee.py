"""LLM 冲突精判：判断两条文本是重复、冲突还是无关。"""

from __future__ import annotations

from iris_agent.core.models import Message

_SYSTEM_PROMPT = (
    "你是数据审查器，判断两条文本之间的关系。只输出一个词：\n"
    "- duplicate 表示两条文本语义重复、表达同一件事；\n"
    "- conflict 表示两条文本语义矛盾、互相冲突；\n"
    "- unrelated 表示两条文本无关。\n"
    "不要输出任何解释，只输出 duplicate、conflict 或 unrelated 其中一个词。"
)


class ConflictReferee:
    def __init__(self, provider):
        self.provider = provider

    def judge(self, a: str, b: str) -> str:
        """Return ``duplicate`` / ``conflict`` / ``unrelated``."""
        messages = [
            Message(role="system", content=_SYSTEM_PROMPT),
            Message(role="user", content=f"A：{a}\nB：{b}"),
        ]
        try:
            response = self.provider.complete(messages, tools=[])
        except Exception:
            return "unrelated"
        label = (response.content or "").strip().lower()
        if "conflict" in label or "冲突" in label or "矛盾" in label:
            return "conflict"
        if "duplicate" in label or "重复" in label or "相同" in label:
            return "duplicate"
        return "unrelated"
