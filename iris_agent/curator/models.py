"""Curator 数据模型：审查报告与建议（白名单字段，最小可落盘结构）。"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

_KINDS = frozenset({"merge", "conflict", "dedupe", "expire", "consolidate"})
_SCOPES = frozenset({"memory", "profile", "skill", "knowledge"})
_REASONS = frozenset({"embedding", "overlap", "llm", "age"})
_REPORT_STATUSES = frozenset({"open", "applied", "dismissed"})
_PROFILE_FIELDS = frozenset({"preferences", "goals", "facts"})
_MEMORY_CATEGORIES = frozenset({"preference", "fact", "project", "other"})

_REPORT_FIELDS = frozenset({"id", "status", "created_at", "summary", "suggestions"})
_SUGGESTION_FIELDS = frozenset(
    {"id", "kind", "scope", "field", "targets", "keep", "drop", "summary", "reason", "applied", "dismissed", "resolution"}
)

_MAX_SUMMARY_CHARS = 400


@dataclass(slots=True)
class CuratorSuggestion:
    """一条审查建议：语义重复/冲突/画像重复，给出保留与删除的目标。"""

    id: str
    kind: str
    scope: str
    field: str | None
    targets: list[str]
    keep: str
    drop: str
    summary: str
    reason: str
    applied: bool = False
    dismissed: bool = False
    resolution: str = ""

    def __post_init__(self) -> None:
        if self.kind not in _KINDS:
            raise ValueError("invalid curator suggestion kind")
        if self.scope not in _SCOPES:
            raise ValueError("invalid curator suggestion scope")
        if self.scope == "profile" and self.field not in _PROFILE_FIELDS:
            raise ValueError("invalid curator suggestion profile field")
        if self.scope in ("memory", "skill", "knowledge") and self.field is not None and self.kind != "consolidate":
            raise ValueError(f"{self.scope} suggestion must not carry a profile field")
        if self.kind == "expire" and self.scope != "knowledge":
            raise ValueError("expire suggestion only applies to knowledge scope")
        if self.kind == "consolidate":
            if self.scope != "memory":
                raise ValueError("consolidate suggestion only applies to memory scope")
            if self.field not in _MEMORY_CATEGORIES:
                raise ValueError("consolidate suggestion requires a memory category field")
            if not self.resolution.strip():
                raise ValueError("consolidate suggestion requires a resolution")
        if self.reason not in _REASONS:
            raise ValueError("invalid curator suggestion reason")
        if not isinstance(self.targets, list) or not all(isinstance(item, str) for item in self.targets):
            raise ValueError("invalid curator suggestion targets")
        if not isinstance(self.keep, str):
            raise ValueError("invalid curator suggestion keep")
        if not isinstance(self.drop, str):
            raise ValueError("invalid curator suggestion drop")
        if self.kind not in ("expire", "consolidate") and not self.keep:
            raise ValueError("invalid curator suggestion keep")
        if self.kind not in ("consolidate",) and not self.drop:
            raise ValueError("invalid curator suggestion drop")
        if not isinstance(self.resolution, str):
            raise ValueError("invalid curator suggestion resolution")
        if not isinstance(self.summary, str) or not self.summary.strip():
            raise ValueError("invalid curator suggestion summary")
        if len(self.summary) > _MAX_SUMMARY_CHARS:
            raise ValueError("curator suggestion summary too long")
        if not isinstance(self.applied, bool):
            raise ValueError("invalid curator suggestion applied flag")
        if not isinstance(self.dismissed, bool):
            raise ValueError("invalid curator suggestion dismissed flag")

    @classmethod
    def new(
        cls,
        kind: str,
        scope: str,
        targets: list[str],
        keep: str,
        drop: str,
        summary: str,
        reason: str,
        field: str | None = None,
        resolution: str = "",
    ) -> "CuratorSuggestion":
        return cls(
            id=f"sug-{uuid4().hex[:12]}",
            kind=kind,
            scope=scope,
            field=field,
            targets=list(targets),
            keep=keep,
            drop=drop,
            summary=summary[: _MAX_SUMMARY_CHARS],
            reason=reason,
            applied=False,
            dismissed=False,
            resolution=resolution,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "kind": self.kind,
            "scope": self.scope,
            "field": self.field,
            "targets": list(self.targets),
            "keep": self.keep,
            "drop": self.drop,
            "summary": self.summary,
            "reason": self.reason,
            "applied": self.applied,
            "dismissed": self.dismissed,
            "resolution": self.resolution,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "CuratorSuggestion":
        if not isinstance(data, dict) or set(data) != _SUGGESTION_FIELDS:
            raise ValueError("invalid curator suggestion")
        return cls(
            id=data["id"],
            kind=data["kind"],
            scope=data["scope"],
            field=data["field"],
            targets=data["targets"],
            keep=data["keep"],
            drop=data["drop"],
            summary=data["summary"],
            reason=data["reason"],
            applied=data["applied"],
            dismissed=data["dismissed"],
            resolution=data["resolution"],
        )


@dataclass(slots=True)
class CuratorReport:
    """一次审查运行产出的报告：多条建议，等待用户确认后应用。"""

    id: str
    status: str
    created_at: str
    summary: str
    suggestions: list[CuratorSuggestion] = field(default_factory=list)

    def __post_init__(self) -> None:
        if not isinstance(self.id, str) or not self.id:
            raise ValueError("invalid curator report id")
        if self.status not in _REPORT_STATUSES:
            raise ValueError("invalid curator report status")
        if not isinstance(self.created_at, str) or not self.created_at:
            raise ValueError("invalid curator report created_at")
        if not isinstance(self.summary, str):
            raise ValueError("invalid curator report summary")
        if not isinstance(self.suggestions, list) or not all(
            isinstance(item, CuratorSuggestion) for item in self.suggestions
        ):
            raise ValueError("invalid curator report suggestions")

    @classmethod
    def new(cls, summary: str, suggestions: list[CuratorSuggestion]) -> "CuratorReport":
        return cls(
            id=f"cur-{uuid4().hex[:12]}",
            status="open",
            created_at=datetime.now(timezone.utc).isoformat(),
            summary=summary,
            suggestions=list(suggestions),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "status": self.status,
            "created_at": self.created_at,
            "summary": self.summary,
            "suggestions": [item.to_dict() for item in self.suggestions],
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "CuratorReport":
        if not isinstance(data, dict) or set(data) != _REPORT_FIELDS:
            raise ValueError("invalid curator report")
        return cls(
            id=data["id"],
            status=data["status"],
            created_at=data["created_at"],
            summary=data["summary"],
            suggestions=[CuratorSuggestion.from_dict(item) for item in data["suggestions"]],
        )
