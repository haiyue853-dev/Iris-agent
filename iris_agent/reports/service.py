from __future__ import annotations

import json
import time
from collections.abc import Callable

from iris_agent.providers.base import ModelProvider
from iris_agent.reports.errors import (
    ReportGenerationError,
    ReportNotFoundError,
    ReportValidationError,
    ReportVersionConflictError,
)
from iris_agent.reports.models import (
    DailyReport,
    ReportSections,
    ReportSourceMessage,
    ReportVersion,
    SECTION_KEYS,
)
from iris_agent.reports.prompts import build_generate_messages
from iris_agent.reports.repository import DailyReportRepository
from iris_agent.sessions.base import SessionRepository


def parse_model_sections(content: str) -> ReportSections:
    try:
        raw = json.loads(content)
        if not isinstance(raw, dict) or set(raw) != set(SECTION_KEYS):
            raise ValueError("unexpected report keys")
        return ReportSections.from_mapping(raw)
    except (json.JSONDecodeError, TypeError, ValueError, ReportValidationError) as exc:
        raise ReportGenerationError(
            "模型返回的日报格式无效",
            code="report_model_output_invalid",
        ) from exc


class DailyReportService:
    def __init__(
        self,
        provider: ModelProvider,
        sessions: SessionRepository,
        repository: DailyReportRepository,
        max_input_chars: int = 50_000,
        max_revision_chars: int = 2_000,
        clock: Callable[[], float] = time.time,
    ):
        self.provider = provider
        self.sessions = sessions
        self.repository = repository
        self.max_input_chars = max_input_chars
        self.max_revision_chars = max_revision_chars
        self.clock = clock

    def generate(
        self,
        report_date: str,
        notes: str,
        session_id: str | None,
        include_chat: bool,
        expected_version: int | None = None,
    ) -> DailyReport:
        notes = notes.strip()
        if len(notes) > self.max_input_chars:
            raise ReportValidationError(
                f"工作记录不能超过 {self.max_input_chars} 字",
                code="report_input_too_long",
            )
        if include_chat and not session_id:
            raise ReportValidationError(
                "导入当前对话时必须提供会话",
                code="report_session_required",
            )

        chat = self._chat_snapshot(session_id) if include_chat and session_id else ()
        existing = self._existing(report_date)
        if existing is None:
            if expected_version not in {None, 0}:
                raise ReportVersionConflictError("日报已被其他操作更新，请刷新后重试")
            versions: list[ReportVersion] = []
            next_version = 1
            created_at = self.clock()
        else:
            if expected_version != existing.current_version:
                raise ReportVersionConflictError("日报已被其他操作更新，请刷新后重试")
            versions = list(existing.versions)
            next_version = max(item.number for item in versions) + 1
            created_at = existing.created_at

        try:
            response = self.provider.complete(build_generate_messages(notes, chat), [])
        except Exception as exc:
            raise ReportGenerationError("生成日报失败，请稍后重试") from exc
        sections = parse_model_sections(response.content)
        now = self.clock()
        versions.append(
            ReportVersion(
                number=next_version,
                sections=sections,
                kind="generated",
                instruction=None,
                created_at=now,
            )
        )
        report = DailyReport.create(
            report_date=report_date,
            source_notes=notes,
            source_session_id=session_id if include_chat else None,
            source_chat_snapshot=chat,
            versions=versions,
            current_version=next_version,
            created_at=created_at,
            updated_at=now,
        )
        self.repository.save(report, expected_version=expected_version)
        return self.repository.get(report_date)

    def _existing(self, report_date: str) -> DailyReport | None:
        try:
            return self.repository.get(report_date)
        except ReportNotFoundError:
            return None

    def _chat_snapshot(self, session_id: str) -> tuple[ReportSourceMessage, ...]:
        session = self.sessions.get(session_id)
        return tuple(
            ReportSourceMessage(message.role, message.content.strip())
            for message in session.messages
            if message.role in {"user", "assistant"} and message.content.strip()
        )
