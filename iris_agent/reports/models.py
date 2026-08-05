from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from datetime import date
import time
from typing import Literal

from iris_agent.reports.errors import ReportValidationError

SECTION_KEYS = ("completed", "in_progress", "problems", "next_day", "assistance")
ReportVersionKind = Literal["generated", "manual", "ai_revision", "restored"]


def _normalize_items(value: object, key: str) -> tuple[str, ...]:
    if not isinstance(value, (list, tuple)) or any(not isinstance(item, str) for item in value):
        raise ReportValidationError(f"日报章节 {key} 必须是字符串数组")
    return tuple(item.strip() for item in value if item.strip())


@dataclass(frozen=True, slots=True)
class ReportSections:
    completed: tuple[str, ...] = ()
    in_progress: tuple[str, ...] = ()
    problems: tuple[str, ...] = ()
    next_day: tuple[str, ...] = ()
    assistance: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        for key in SECTION_KEYS:
            object.__setattr__(self, key, _normalize_items(getattr(self, key), key))

    @classmethod
    def from_mapping(cls, raw: Mapping[str, object]) -> ReportSections:
        if set(raw) != set(SECTION_KEYS):
            raise ReportValidationError("日报章节字段无效")
        return cls(**{key: _normalize_items(raw[key], key) for key in SECTION_KEYS})

    def to_dict(self) -> dict[str, list[str]]:
        return {key: list(getattr(self, key)) for key in SECTION_KEYS}


@dataclass(frozen=True, slots=True)
class ReportSourceMessage:
    role: Literal["user", "assistant"]
    content: str

    def __post_init__(self) -> None:
        if self.role not in {"user", "assistant"}:
            raise ReportValidationError("日报来源消息角色无效")
        if not isinstance(self.content, str):
            raise ReportValidationError("日报来源消息内容必须是文本")


@dataclass(frozen=True, slots=True)
class ReportVersion:
    number: int
    sections: ReportSections
    kind: ReportVersionKind
    instruction: str | None
    created_at: float

    def __post_init__(self) -> None:
        if self.number < 1:
            raise ReportValidationError("日报版本号必须大于 0")
        if self.kind not in {"generated", "manual", "ai_revision", "restored"}:
            raise ReportValidationError("日报版本类型无效")
        if self.instruction is not None and not isinstance(self.instruction, str):
            raise ReportValidationError("日报修改说明必须是文本")


@dataclass(slots=True)
class DailyReport:
    date: str
    source_notes: str
    source_session_id: str | None
    source_chat_snapshot: tuple[ReportSourceMessage, ...]
    versions: list[ReportVersion] = field(default_factory=list)
    current_version: int = 0
    created_at: float = 0.0
    updated_at: float = 0.0

    @classmethod
    def create(
        cls,
        report_date: str,
        source_notes: str,
        source_session_id: str | None,
        source_chat_snapshot: Iterable[ReportSourceMessage],
        versions: Iterable[ReportVersion],
        current_version: int,
        created_at: float | None = None,
        updated_at: float | None = None,
    ) -> DailyReport:
        try:
            date.fromisoformat(report_date)
        except (TypeError, ValueError) as exc:
            raise ReportValidationError("日报日期必须使用 YYYY-MM-DD 格式", code="report_invalid_date") from exc
        now = time.time()
        report = cls(
            date=report_date,
            source_notes=str(source_notes),
            source_session_id=source_session_id,
            source_chat_snapshot=tuple(source_chat_snapshot),
            versions=list(versions),
            current_version=current_version,
            created_at=created_at if created_at is not None else now,
            updated_at=updated_at if updated_at is not None else now,
        )
        numbers = [item.number for item in report.versions]
        if len(numbers) != len(set(numbers)):
            raise ReportValidationError("日报版本号不能重复")
        _ = report.current
        return report

    @property
    def current(self) -> ReportVersion:
        for version in self.versions:
            if version.number == self.current_version:
                return version
        raise ReportValidationError("当前日报版本不存在")
