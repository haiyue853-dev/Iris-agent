"""Query-aware page summarizer.

The fetcher hands a long page to ``summarize``; we ask the LLM to produce a
short, query-aware summary so the Agent loop only ever sees a few hundred
characters. This decouples tool-output size from the source page length,
which is the main driver of the "60k tokens for 5 fetches" pathology.

The summarizer is intentionally minimal: it never raises. On any LLM error
it returns the head of the raw text so the Agent still has something to work
with, capped at ``max_summary_chars``.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from iris_agent.core.models import Message

if TYPE_CHECKING:
    from iris_agent.providers.base import ModelProvider

logger = logging.getLogger(__name__)


# 输入截断：6k 字符足够覆盖大多数新闻/教程类页面，摘要本身不会爆 token
_INPUT_TRUNCATE_CHARS = 6000
# 输出硬上限：单次 fetch_page 的工具结果必须 ≤ 1k 字符
_DEFAULT_MAX_SUMMARY_CHARS = 800


class PageSummarizer:
    """Compress fetched pages into short, query-aware summaries.

    Parameters
    ----------
    provider:
        LLM provider used to generate the summary. May be a provider that has
        not been opened yet (we only call ``complete`` which is non-streaming
        and side-effect free).
    max_summary_chars:
        Hard upper bound on the returned summary length. The Agent loop will
        see at most this many characters per page.
    input_truncate_chars:
        How much of the raw page text we feed the summarizer. Larger values
        improve summary quality at the cost of more summarizer-side tokens.
    """

    def __init__(
        self,
        provider: "ModelProvider",
        max_summary_chars: int = _DEFAULT_MAX_SUMMARY_CHARS,
        input_truncate_chars: int = _INPUT_TRUNCATE_CHARS,
    ) -> None:
        if max_summary_chars <= 0:
            raise ValueError("max_summary_chars must be > 0")
        if input_truncate_chars <= 0:
            raise ValueError("input_truncate_chars must be > 0")
        self.provider = provider
        self.max_summary_chars = max_summary_chars
        self.input_truncate_chars = input_truncate_chars

    def summarize(self, url: str, raw_text: str, query_hint: str | None = None) -> str:
        """Return a short summary of ``raw_text`` for the given ``url``.

        Never raises. On any failure returns the head of the raw text capped
        at ``max_summary_chars`` so the Agent always has a usable result.
        """
        if not raw_text:
            return ""
        try:
            return self._call_llm(url, raw_text, query_hint)
        except Exception as exc:  # noqa: BLE001 - summarizer is best-effort
            logger.warning("PageSummarizer 失败，回退原文头部: %s", exc)
            return raw_text[: self.max_summary_chars]

    def _call_llm(self, url: str, raw_text: str, query_hint: str | None) -> str:
        truncated = raw_text[: self.input_truncate_chars]
        query_block = (
            f"\n\n用户的搜索意图：{query_hint.strip()}" if query_hint and query_hint.strip() else ""
        )
        messages = [
            Message(
                role="system",
                content=(
                    "你是网页摘要助手。把网页内容压缩成 200-500 字的简洁中文摘要。"
                    "只保留与用户意图相关的事实、人物、机构、数字、关键论点和 URL。"
                    "去除导航、广告、版权声明、重复段落。"
                    "输出纯文本，禁止使用 Markdown 标题、列表符号或引用块。"
                ),
            ),
            Message(
                role="user",
                content=f"URL: {url}\n\n网页正文：\n{truncated}{query_block}",
            ),
        ]
        response = self.provider.complete(messages, tools=[])
        summary = (response.content or "").strip()
        if not summary:
            return raw_text[: self.max_summary_chars]
        return summary[: self.max_summary_chars]
