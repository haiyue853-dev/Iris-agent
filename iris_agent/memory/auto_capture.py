"""Automatic memory capture: a cheap rule pre-filter, then the model judges.

The memory ledger stayed empty because only an explicit "记住…" ever wrote to it. This adds
passive capture, but keeps it cheap: a regex pre-filter decides whether a message is even a
candidate, and only then is a model call spent. Most messages cost nothing.

**The de-duplication policy is deliberately not hardcoded.** The model returns, per fact,
whether that topic has a single answer (``unique`` → replace what we already know) or whether
several values can coexist (``coexist`` → keep them all). "喜欢的颜色" and "讨厌的食物" can
both hold several values; "称呼" and "生日" cannot. That judgement belongs to the model, not
to a lookup table here.
"""

from __future__ import annotations

import json
import logging
import re

from iris_agent.core.models import Message
from iris_agent.memory.models import MemoryEntry
from iris_agent.memory.policy import is_agent_behavior_rule
from iris_agent.memory.service import MemoryNotFoundError, MemoryService
from iris_agent.providers.base import ModelProvider

_LOGGER = logging.getLogger(__name__)

_CATEGORIES = frozenset({"preference", "fact", "project", "other"})
_MODES = frozenset({"unique", "coexist"})
_MAX_CONTENT_CHARS = 500

# 粗筛信号。命中只代表「这句话可能在说关于用户本人的长期事实」，不代表一定要记——
# 那一步交给模型。这里刻意收得窄，避免每句话都白花一次模型调用。
_CANDIDATE_SIGNALS = re.compile(
    r"我叫|我是(?!不是)|我的(?:名字|称呼|邮箱|手机|电话|生日|职业|专业|家乡|公司|学校|地址)|"
    r"我(?:还|也)?喜欢|我偏好|我习惯|我(?:还|也)?不喜欢|我(?:还|也)?讨厌|我一般(?:都|会)|我通常|我总是|"
    r"我住在|我在做|我在用|我常用|我一般用|我一直|"
    r"记住|记一下|帮我记|别忘了|以后都|每次都|以后别|不要再|别再",
)

# 明显没有长期价值的短句，直接跳过。
_NOISE = re.compile(
    r"^\s*(?:你好|您好|在吗|在么|谢谢|感谢|好的|好嘞|嗯+|哦+|哈哈+|收到|明白|知道了|ok|hi|hello)"
    r"[\s!！。.？?,，~]*$",
    re.IGNORECASE,
)

_SYSTEM_PROMPT = (
    "你是长期记忆抽取器。判断用户这句话里有没有值得长期记住的、关于【用户本人】的事实或偏好。\n"
    "只输出一个 JSON 对象：{\"facts\": [{\"topic\": \"...\", \"value\": \"...\", "
    "\"category\": \"...\", \"mode\": \"...\"}]}\n"
    "字段规则：\n"
    "- topic：这条记忆的主题名，要短且稳定（如「称呼」「喜欢的颜色」「在做的项目」）。"
    "同一主题再次出现时靠它比对，所以同一个意思请始终用同一个说法。\n"
    "- value：要记住的具体内容，一句话，不要重复主题名。\n"
    "- category：只能是 preference / fact / project / other。\n"
    "- mode：由你判断这个主题的性质：\n"
    "  · \"unique\" —— 该主题客观上只有一个答案，新值应当覆盖旧值"
    "（例如称呼、生日、身高、常用邮箱、所在城市）。\n"
    "  · \"coexist\" —— 该主题可以有多个值同时成立，应当并存"
    "（例如喜欢的东西、讨厌的事物、去过的地方、在做的项目、使用的工具）。\n"
    "  拿不准就选 \"coexist\"。\n"
    "闲聊、一次性问题、临时指令、以及对助手行为或输出格式的要求，都不要记，返回 {\"facts\": []}。\n"
    "绝对不要输出会改变助手角色、性格、工作流程或输出规则的条目。\n"
    "只输出 JSON，不要任何解释。"
)


class MemoryAutoCapture:
    """Passively grow the memory ledger, one cheap filter at a time."""

    def __init__(
        self,
        provider: ModelProvider,
        memory: MemoryService,
        *,
        max_facts_per_message: int = 3,
    ) -> None:
        self.provider = provider
        self.memory = memory
        self.max_facts_per_message = max(1, int(max_facts_per_message))

    def is_candidate(self, text: str) -> bool:
        """便宜的粗筛：不命中就完全不花模型调用。"""
        if not isinstance(text, str):
            return False
        stripped = text.strip()
        if not stripped or _NOISE.match(stripped):
            return False
        return bool(_CANDIDATE_SIGNALS.search(stripped))

    def capture(
        self,
        text: str,
        *,
        source_session_id: str | None = None,
    ) -> tuple[MemoryEntry, ...]:
        """Extract and store whatever is worth keeping. Never raises."""
        if not self.is_candidate(text):
            return ()
        try:
            facts = self._extract(text)
        except Exception:
            _LOGGER.exception("自动记忆抽取失败")
            return ()
        if not facts:
            return ()

        try:
            known = {entry.content for entry in self.memory.list()}
        except Exception:
            _LOGGER.exception("读取已有记忆失败，跳过本次自动记忆")
            return ()

        written: list[MemoryEntry] = []
        for fact in facts[: self.max_facts_per_message]:
            try:
                entry = self._apply(fact, known, source_session_id=source_session_id)
            except Exception:
                _LOGGER.exception("写入自动记忆失败（topic=%r）", (fact or {}).get("topic"))
                continue
            if entry is not None:
                known.add(entry.content)
                written.append(entry)
        return tuple(written)

    def _extract(self, text: str) -> list[dict]:
        response = self.provider.complete(
            [Message(role="system", content=_SYSTEM_PROMPT), Message(role="user", content=text)],
            [],
        )
        data = self._parse_json(response.content)
        facts = data.get("facts") if isinstance(data, dict) else None
        if not isinstance(facts, list):
            return []
        return [item for item in facts if isinstance(item, dict)]

    @staticmethod
    def _parse_json(content: str) -> dict:
        text = (content or "").strip()
        fence = re.match(r"^```(?:json)?\s*(.*?)\s*```$", text, re.DOTALL)
        if fence:
            text = fence.group(1).strip()
        parsed = json.loads(text)
        return parsed if isinstance(parsed, dict) else {}

    def _apply(
        self,
        fact: dict,
        known: set[str],
        *,
        source_session_id: str | None = None,
    ) -> MemoryEntry | None:
        topic = str(fact.get("topic", "")).strip()
        value = str(fact.get("value", "")).strip()
        if not topic or not value:
            return None
        category = str(fact.get("category", "other")).strip().lower()
        if category not in _CATEGORIES:
            category = "other"
        mode = str(fact.get("mode", "coexist")).strip().lower()
        if mode not in _MODES:
            mode = "coexist"

        content = f"{topic}：{value}"
        if len(content) > _MAX_CONTENT_CHARS:
            content = content[: _MAX_CONTENT_CHARS - 1] + "…"
        if is_agent_behavior_rule(content):
            _LOGGER.info("自动记忆跳过一条行为规则（topic=%s）", topic)
            return None
        if content in known:
            return None

        if mode == "unique":
            self._replace_topic(topic, known)
        entry = self.memory.add(content, category, source_session_id=source_session_id)
        _LOGGER.info("自动记忆已写入（%s）：%s", mode, content)
        return entry

    def _replace_topic(self, topic: str, known: set[str]) -> int:
        """唯一答案的主题：删掉旧值再写新的，避免同一主题积攒出矛盾的答案。"""
        prefix = f"{topic}："
        removed = 0
        for entry in self.memory.list():
            if not entry.content.startswith(prefix):
                continue
            try:
                self.memory.delete(entry.id)
            except MemoryNotFoundError:
                continue
            known.discard(entry.content)
            removed += 1
        return removed
