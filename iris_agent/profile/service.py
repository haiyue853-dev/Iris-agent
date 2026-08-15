"""Profile service: merge, render, and throttled auto-extraction."""

from __future__ import annotations

from datetime import datetime, timezone

from iris_agent.profile.extractor import ProfileExtractor
from iris_agent.profile.models import ProfilePatch, UserProfile
from iris_agent.profile.repository import ProfileRepository

_MAX_RENDER_CHARS = 800


class ProfileService:
    def __init__(
        self,
        repository: ProfileRepository,
        extractor: ProfileExtractor,
        max_items_per_field: int = 20,
        max_item_chars: int = 200,
        extract_interval_rounds: int = 10,
        enabled: bool = True,
    ):
        self.repository = repository
        self.extractor = extractor
        self.max_items_per_field = max_items_per_field
        self.max_item_chars = max_item_chars
        self.extract_interval_rounds = extract_interval_rounds
        self.enabled = enabled
        self._rounds_since_extract = 0

    def get(self) -> UserProfile:
        return self.repository.load()

    def apply_patch(self, patch: ProfilePatch) -> UserProfile:
        with self.repository.lock:
            profile = self.repository.load()
            merged = self._merge(profile, patch)
            if merged != profile:
                merged.updated_at = datetime.now(timezone.utc).isoformat()
            self.repository.save(merged)
            return merged

    def render(self) -> str:
        profile = self.get()
        if not self._has_content(profile):
            return ""
        parts: list[str] = []
        if profile.name:
            parts.append(f"称呼：{profile.name}")
        if profile.preferences:
            parts.append("偏好：" + "、".join(profile.preferences))
        if profile.goals:
            parts.append("目标：" + "、".join(profile.goals))
        if profile.style:
            parts.append("风格：" + profile.style)
        if profile.facts:
            parts.append("事实：" + "、".join(profile.facts))
        text = "[画像] " + "；".join(parts)
        return text[: _MAX_RENDER_CHARS]

    def maybe_update(self, dialogue: str) -> bool:
        if not self.enabled:
            return False
        profile = self.get()
        if not self._has_content(profile):
            return self._extract_and_apply(dialogue)
        self._rounds_since_extract += 1
        if self._rounds_since_extract >= self.extract_interval_rounds:
            return self._extract_and_apply(dialogue)
        return False

    def _extract_and_apply(self, dialogue: str) -> bool:
        patch = self.extractor.extract(dialogue)
        if self._is_empty_patch(patch):
            self._rounds_since_extract = 0
            return False
        self.apply_patch(patch)
        self._rounds_since_extract = 0
        return True

    def _merge(self, profile: UserProfile, patch: ProfilePatch) -> UserProfile:
        merged = UserProfile(
            name=profile.name,
            preferences=list(profile.preferences),
            goals=list(profile.goals),
            style=profile.style,
            facts=list(profile.facts),
            updated_at=profile.updated_at,
        )
        if patch.name is not None and patch.name.strip():
            merged.name = patch.name.strip()
        if patch.style is not None and patch.style.strip():
            merged.style = patch.style.strip()
        for field, items in (("preferences", patch.preferences), ("goals", patch.goals), ("facts", patch.facts)):
            if items is None:
                continue
            current = list(getattr(merged, field))
            for item in items:
                trimmed = item[: self.max_item_chars]
                if trimmed and trimmed not in current:
                    current.append(trimmed)
            setattr(merged, field, current[: self.max_items_per_field])
        return merged

    @staticmethod
    def _has_content(profile: UserProfile) -> bool:
        return bool(profile.name or profile.preferences or profile.goals or profile.style or profile.facts)

    @staticmethod
    def _is_empty_patch(patch: ProfilePatch) -> bool:
        return (
            patch.name is None
            and patch.preferences is None
            and patch.goals is None
            and patch.style is None
            and patch.facts is None
        )
