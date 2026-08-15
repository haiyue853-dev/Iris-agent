"""User profile models (structured user snapshot)."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

_PERSISTED_FIELDS = frozenset({"name", "preferences", "goals", "style", "facts", "updated_at"})
_LIST_FIELDS = frozenset({"preferences", "goals", "facts"})


@dataclass(slots=True)
class UserProfile:
    """A single structured snapshot of who the user is."""

    name: str = ""
    preferences: list[str] = field(default_factory=list)
    goals: list[str] = field(default_factory=list)
    style: str = ""
    facts: list[str] = field(default_factory=list)
    updated_at: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "preferences": list(self.preferences),
            "goals": list(self.goals),
            "style": self.style,
            "facts": list(self.facts),
            "updated_at": self.updated_at,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "UserProfile":
        if not isinstance(data, dict) or set(data) != _PERSISTED_FIELDS:
            raise ValueError("invalid user profile")
        profile = cls()
        profile.name = _require_str(data["name"], "name")
        for key in _LIST_FIELDS:
            value = data[key]
            if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
                raise ValueError(f"invalid user profile field: {key}")
            setattr(profile, key, list(value))
        profile.style = _require_str(data["style"], "style")
        profile.updated_at = _require_str(data["updated_at"], "updated_at")
        return profile


@dataclass(slots=True)
class ProfilePatch:
    """Incremental profile update produced by the extractor. None = no update."""

    name: str | None = None
    preferences: list[str] | None = None
    goals: list[str] | None = None
    style: str | None = None
    facts: list[str] | None = None


def _require_str(value: Any, field_name: str) -> str:
    if not isinstance(value, str):
        raise ValueError(f"invalid user profile field: {field_name}")
    return value
