"""Profile extractor: pull structured user-profile deltas out of dialogue."""

from __future__ import annotations

import json
import re

from iris_agent.core.models import Message
from iris_agent.profile.models import ProfilePatch
from iris_agent.providers.base import ModelProvider

_SYSTEM_PROMPT = (
    "你是用户画像提取器。分析下面的对话，提取关于【用户】的长期画像信息。"
    "只返回一个 JSON 对象，字段可选：name（用户称呼）、preferences（偏好列表）、"
    "goals（目标列表）、style（沟通风格）、facts（长期事实列表）。"
    "没有把握的字段不要输出。只输出 JSON，不要任何解释。"
)

_KNOWN_FIELDS = frozenset({"name", "preferences", "goals", "style", "facts"})


class ProfileExtractor:
    def __init__(self, provider: ModelProvider):
        self.provider = provider

    def extract(self, dialogue: str) -> ProfilePatch:
        try:
            response = self.provider.complete(
                [Message(role="system", content=_SYSTEM_PROMPT), Message(role="user", content=dialogue)],
                [],
            )
            data = self._parse_json(response.content)
            return self._to_patch(data)
        except Exception:
            return ProfilePatch()

    @staticmethod
    def _parse_json(content: str) -> dict:
        text = content.strip()
        # Strip a markdown code fence if present.
        fence = re.match(r"^```(?:json)?\s*(.*?)\s*```$", text, re.DOTALL)
        if fence:
            text = fence.group(1).strip()
        parsed = json.loads(text)
        if not isinstance(parsed, dict):
            return {}
        return parsed

    @staticmethod
    def _to_patch(data: dict) -> ProfilePatch:
        patch = ProfilePatch()
        if not data:
            return patch
        for field in _KNOWN_FIELDS:
            if field not in data or data[field] is None:
                continue
            value = data[field]
            if field == "name" and isinstance(value, str) and value.strip():
                patch.name = value.strip()
            elif field == "style" and isinstance(value, str) and value.strip():
                patch.style = value.strip()
            elif field in {"preferences", "goals", "facts"} and isinstance(value, list):
                items = [str(item).strip() for item in value if isinstance(item, str) and str(item).strip()]
                if items:
                    setattr(patch, field, items)
        return patch
