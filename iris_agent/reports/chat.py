from __future__ import annotations

import json
import threading
import time
from dataclasses import dataclass
from uuid import uuid4

from iris_agent.core.models import Message
from iris_agent.providers.base import ModelProvider
from iris_agent.reports.errors import (
    ReportGenerationError,
    ReportSuggestionAlreadyAppliedError,
    ReportSuggestionNotFoundError,
    ReportValidationError,
    ReportVersionConflictError,
)
from iris_agent.reports.models import DailyReport, ReportSections, ReportVersion
from iris_agent.reports.repository import DailyReportRepository


_CHAT_SYSTEM_PROMPT = """You assist with a daily report. Reply strictly with one JSON object and no markdown.
Its keys must be exactly reply, sections, attachment_ids. reply must be a concise string.
sections must have exactly completed, in_progress, problems, next_day, assistance, each an array of strings.
attachment_ids must only contain IDs from the provided attachments. Do not invent facts."""


@dataclass(frozen=True, slots=True)
class ReportSuggestion:
    id: str
    report_date: str
    base_revision: int
    reply: str
    sections: ReportSections
    attachment_ids: tuple[str, ...]
    applied: bool = False


@dataclass(frozen=True, slots=True)
class ReportChatMessage:
    reply: str
    suggestion: ReportSuggestion

    @property
    def id(self) -> str:
        return self.suggestion.id

    @property
    def sections(self) -> ReportSections:
        return self.suggestion.sections

    @property
    def attachment_ids(self) -> tuple[str, ...]:
        return self.suggestion.attachment_ids


class DailyReportChatService:
    def __init__(self, provider: ModelProvider, repository: DailyReportRepository):
        self.provider = provider
        self.repository = repository
        self._suggestions: dict[str, ReportSuggestion] = {}
        self._lock = threading.RLock()

    def chat(
        self,
        report_date: str,
        message: str,
        attachment_ids: list[str] | tuple[str, ...],
        expected_version: int,
    ) -> ReportChatMessage:
        current = self.repository.get(report_date)
        self._check_version(current, expected_version)
        selected = self._selected_attachments(current, attachment_ids)
        try:
            response = self.provider.complete(self._messages(current, message, selected), tools=[])
        except Exception as exc:
            raise ReportGenerationError("日报对话失败，请稍后重试") from exc
        reply, sections, used_ids = self._parse_response(response.content, {item["id"] for item in selected})
        suggestion = ReportSuggestion(str(uuid4()), report_date, current.revision, reply, sections, used_ids)
        with self._lock:
            self._suggestions[suggestion.id] = suggestion
        return ReportChatMessage(reply=reply, suggestion=suggestion)

    def apply_suggestion(self, report_date: str, suggestion_id: str, expected_version: int) -> DailyReport:
        with self.repository.report_lock(report_date):
            current = self.repository.get(report_date)
            self._check_version(current, expected_version)
            with self._lock:
                suggestion = self._suggestions.get(suggestion_id)
                if suggestion is None or suggestion.report_date != report_date:
                    raise ReportSuggestionNotFoundError("日报建议不存在")
                if suggestion.applied:
                    raise ReportSuggestionAlreadyAppliedError("日报建议已被应用")
                if suggestion.base_revision != current.revision:
                    raise ReportVersionConflictError("日报已被其他操作更新，请刷新后重试")
                updated = self._append_ai_revision(current, suggestion)
                self.repository.save(updated, expected_version=expected_version)
                self._suggestions[suggestion_id] = ReportSuggestion(
                    suggestion.id, suggestion.report_date, suggestion.base_revision, suggestion.reply,
                    suggestion.sections, suggestion.attachment_ids, applied=True,
                )
        return self.repository.get(report_date)

    @staticmethod
    def _check_version(report: DailyReport, expected_version: int) -> None:
        if report.revision != expected_version:
            raise ReportVersionConflictError("日报已被其他操作更新，请刷新后重试")

    @staticmethod
    def _selected_attachments(report: DailyReport, attachment_ids: list[str] | tuple[str, ...]) -> list[dict[str, str]]:
        requested = list(attachment_ids)
        if len(requested) != len(set(requested)) or any(not isinstance(item, str) for item in requested):
            raise ReportValidationError("日报附件无效", code="report_attachment_not_found")
        available = {item.id: item for item in report.attachments}
        if any(item not in available for item in requested):
            raise ReportValidationError("日报附件不存在", code="report_attachment_not_found")
        return [
            {"id": available[item].id, "name": available[item].original_name, "text": available[item].extracted_text or ""}
            for item in requested
        ]

    @staticmethod
    def _messages(report: DailyReport, message: str, attachments: list[dict[str, str]]) -> list[Message]:
        payload = {
            "current_report": report.current.sections.to_dict(),
            "message": message,
            "attachments": attachments,
        }
        return [
            Message(role="system", content=_CHAT_SYSTEM_PROMPT),
            Message(role="user", content=json.dumps(payload, ensure_ascii=False)),
        ]

    @staticmethod
    def _parse_response(content: str, allowed_attachment_ids: set[str]) -> tuple[str, ReportSections, tuple[str, ...]]:
        try:
            raw = json.loads(content)
            if not isinstance(raw, dict) or set(raw) != {"reply", "sections", "attachment_ids"}:
                raise ValueError("unexpected chat keys")
            reply = raw["reply"]
            attachment_ids = raw["attachment_ids"]
            if not isinstance(reply, str) or not reply.strip() or not isinstance(attachment_ids, list):
                raise ValueError("invalid chat fields")
            if any(not isinstance(item, str) for item in attachment_ids) or len(attachment_ids) != len(set(attachment_ids)):
                raise ValueError("invalid attachment ids")
            if not set(attachment_ids).issubset(allowed_attachment_ids):
                raise ValueError("unknown attachment id")
            return reply.strip(), ReportSections.from_mapping(raw["sections"]), tuple(attachment_ids)
        except (json.JSONDecodeError, TypeError, ValueError, ReportValidationError) as exc:
            raise ReportGenerationError("模型返回的日报对话格式无效", code="report_model_output_invalid") from exc

    @staticmethod
    def _append_ai_revision(report: DailyReport, suggestion: ReportSuggestion) -> DailyReport:
        now = time.time()
        next_number = max(version.number for version in report.versions) + 1
        return DailyReport.create(
            report.date, report.source_notes, report.source_session_id, report.source_chat_snapshot,
            [*report.versions, ReportVersion(next_number, suggestion.sections, "ai_revision", suggestion.reply, now)],
            next_number, report.created_at, now, report.attachments, report.revision + 1,
        )
