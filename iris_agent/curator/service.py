"""Curator service: run read-only reviews, then apply/dismiss suggestions on user confirmation."""

from __future__ import annotations

import time
from dataclasses import dataclass

from iris_agent.curator.models import CuratorReport, CuratorSuggestion
from iris_agent.curator.repository import CuratorRepository
from iris_agent.curator.similarity import SimilarityEngine
from iris_agent.memory.service import MemoryNotFoundError, MemoryService
from iris_agent.profile.service import ProfileService

_EXCERPT_CHARS = 40
_PROFILE_FIELDS = ("preferences", "goals", "facts")
_SCOPE_LABELS = {"memory": "记忆", "profile": "画像", "skill": "技能", "knowledge": "知识"}
_SECONDS_PER_DAY = 86400


class CuratorReportNotFoundError(RuntimeError):
    """The requested curator report does not exist."""


def _excerpt(text: str, n: int = _EXCERPT_CHARS) -> str:
    text = text.strip()
    return text if len(text) <= n else text[: n] + "…"


@dataclass(slots=True)
class _Candidate:
    scope: str
    field: str | None
    ref_a: str
    ref_b: str
    text_a: str
    text_b: str
    keep: str
    drop: str


class CuratorService:
    def __init__(
        self,
        repository: CuratorRepository,
        memory: MemoryService,
        profile: ProfileService,
        engine: SimilarityEngine,
        skills=None,
        knowledge=None,
        referee=None,
        enable_llm: bool = True,
        max_pairs_per_run: int = 200,
        expire_days: int = 90,
        consolidate_enabled: bool = True,
        consolidate_min_entries: int = 4,
    ):
        self.repository = repository
        self.memory = memory
        self.profile = profile
        self.engine = engine
        self.skills = skills
        self.knowledge = knowledge
        self.referee = referee
        self.enable_llm = enable_llm
        self.max_pairs_per_run = max_pairs_per_run
        self.expire_days = expire_days
        self.consolidate_enabled = consolidate_enabled
        self.consolidate_min_entries = consolidate_min_entries

    def run(self) -> CuratorReport:
        candidates = self._build_candidates()
        suggestions = self._review(candidates)
        suggestions.extend(self._build_expire_suggestions())
        suggestions.extend(self._build_consolidate_suggestions())
        report = CuratorReport.new(self._summarize(suggestions), suggestions)
        self.repository.save(report)
        return report

    def list_reports(self) -> list[CuratorReport]:
        return self.repository.list()

    def get_report(self, report_id: str) -> CuratorReport:
        report = self.repository.get(report_id)
        if report is None:
            raise CuratorReportNotFoundError(report_id)
        return report

    def apply(self, report_id: str, suggestion_ids: list[str] | None = None) -> int:
        report = self.get_report(report_id)
        applied = 0
        for suggestion in report.suggestions:
            if suggestion.applied or suggestion.dismissed:
                continue
            if suggestion_ids is not None and suggestion.id not in suggestion_ids:
                continue
            if self._apply_one(suggestion):
                suggestion.applied = True
                applied += 1
        report.status = self._derive_status(report)
        self.repository.save(report)
        return applied

    def dismiss(self, report_id: str, suggestion_ids: list[str] | None = None) -> int:
        report = self.get_report(report_id)
        dismissed = 0
        for suggestion in report.suggestions:
            if suggestion.applied or suggestion.dismissed:
                continue
            if suggestion_ids is not None and suggestion.id not in suggestion_ids:
                continue
            suggestion.dismissed = True
            dismissed += 1
        report.status = self._derive_status(report)
        self.repository.save(report)
        return dismissed

    def _build_candidates(self) -> list[_Candidate]:
        candidates: list[_Candidate] = []

        by_category: dict[str, list] = {}
        for entry in self.memory.list():
            by_category.setdefault(entry.category, []).append(entry)
        for entries in by_category.values():
            entries.sort(key=lambda item: item.updated_at, reverse=True)
            for i in range(len(entries)):
                for j in range(i + 1, len(entries)):
                    candidates.append(
                        _Candidate(
                            scope="memory",
                            field=None,
                            ref_a=entries[i].id,
                            ref_b=entries[j].id,
                            text_a=entries[i].content,
                            text_b=entries[j].content,
                            keep=entries[i].id,
                            drop=entries[j].id,
                        )
                    )
                    if len(candidates) >= self.max_pairs_per_run:
                        return candidates

        profile = self.profile.get()
        for field in _PROFILE_FIELDS:
            items = list(getattr(profile, field))
            for i in range(len(items)):
                for j in range(i + 1, len(items)):
                    candidates.append(
                        _Candidate(
                            scope="profile",
                            field=field,
                            ref_a=items[i],
                            ref_b=items[j],
                            text_a=items[i],
                            text_b=items[j],
                            keep=items[i],
                            drop=items[j],
                        )
                    )
                    if len(candidates) >= self.max_pairs_per_run:
                        return candidates

        if self.skills is not None:
            user_skills = self.skills.list_user_definitions()
            for i in range(len(user_skills)):
                for j in range(i + 1, len(user_skills)):
                    candidates.append(
                        _Candidate(
                            scope="skill",
                            field=None,
                            ref_a=user_skills[i].id,
                            ref_b=user_skills[j].id,
                            text_a=f"{user_skills[i].name}\n{user_skills[i].body}",
                            text_b=f"{user_skills[j].name}\n{user_skills[j].body}",
                            keep=user_skills[i].id,
                            drop=user_skills[j].id,
                        )
                    )
                    if len(candidates) >= self.max_pairs_per_run:
                        return candidates

        if self.knowledge is not None:
            by_category = {}
            for entry in self.knowledge.list():
                by_category.setdefault(entry.category, []).append(entry)
            for entries in by_category.values():
                entries.sort(key=lambda item: item.updated_at, reverse=True)
                for i in range(len(entries)):
                    for j in range(i + 1, len(entries)):
                        candidates.append(
                            _Candidate(
                                scope="knowledge",
                                field=None,
                                ref_a=entries[i].id,
                                ref_b=entries[j].id,
                                text_a=f"{entries[i].title}\n{entries[i].content}",
                                text_b=f"{entries[j].title}\n{entries[j].content}",
                                keep=entries[i].id,
                                drop=entries[j].id,
                            )
                        )
                        if len(candidates) >= self.max_pairs_per_run:
                            return candidates
        return candidates

    def _build_expire_suggestions(self) -> list[CuratorSuggestion]:
        if self.knowledge is None or self.expire_days <= 0:
            return []
        now = time.time()
        threshold = now - self.expire_days * _SECONDS_PER_DAY
        suggestions: list[CuratorSuggestion] = []
        for entry in self.knowledge.list():
            if entry.created_at >= threshold:
                continue
            days = int((now - entry.created_at) / _SECONDS_PER_DAY)
            suggestions.append(
                CuratorSuggestion.new(
                    kind="expire",
                    scope="knowledge",
                    targets=[entry.id],
                    keep="",
                    drop=entry.id,
                    summary=f"知识过期：{_excerpt(entry.title)}（{days} 天前收录）",
                    reason="age",
                )
            )
        return suggestions

    def _build_consolidate_suggestions(self) -> list[CuratorSuggestion]:
        if not self.consolidate_enabled or self.referee is None:
            return []
        by_category: dict[str, list] = {}
        for entry in self.memory.list():
            by_category.setdefault(entry.category, []).append(entry)
        suggestions: list[CuratorSuggestion] = []
        for category, entries in by_category.items():
            if len(entries) < self.consolidate_min_entries:
                continue
            texts = [entry.content for entry in entries]
            resolution = self.referee.consolidate(texts)
            if not resolution:
                continue
            ids = [entry.id for entry in entries]
            suggestions.append(
                CuratorSuggestion.new(
                    kind="consolidate",
                    scope="memory",
                    targets=ids,
                    keep="",
                    drop="",
                    summary=f"记忆归纳：把 {len(ids)} 条「{_SCOPE_LABELS.get(category, category)}」记忆合并为 1 条",
                    reason="llm",
                    field=category,
                    resolution=resolution,
                )
            )
        return suggestions

    def _review(self, candidates: list[_Candidate]) -> list[CuratorSuggestion]:
        if not candidates:
            return []
        scores, mode = self.engine.score_pairs([(c.text_a, c.text_b) for c in candidates])
        suggestions: list[CuratorSuggestion] = []
        for candidate, score in zip(candidates, scores):
            verdict = self.engine.bucket(score)
            if verdict == "duplicate":
                kind = "merge" if candidate.scope == "memory" else "dedupe"
                suggestions.append(self._make(candidate, kind, mode))
            elif verdict == "review" and self.enable_llm and self.referee is not None:
                label = self.referee.judge(candidate.text_a, candidate.text_b)
                if label == "duplicate":
                    kind = "merge" if candidate.scope == "memory" else "dedupe"
                    suggestions.append(self._make(candidate, kind, "llm"))
                elif label == "conflict":
                    suggestions.append(self._make(candidate, "conflict", "llm"))
        return suggestions

    @staticmethod
    def _make(candidate: _Candidate, kind: str, reason: str) -> CuratorSuggestion:
        a = _excerpt(candidate.text_a)
        b = _excerpt(candidate.text_b)
        label = _SCOPE_LABELS[candidate.scope]
        action = "冲突" if kind == "conflict" else "重复"
        if candidate.scope == "profile":
            summary = f"{label}{action}（{candidate.field}）：{a} ↔ {b}"
        else:
            summary = f"{label}{action}：{a} ↔ {b}"
        return CuratorSuggestion.new(
            kind=kind,
            scope=candidate.scope,
            targets=[candidate.ref_a, candidate.ref_b],
            keep=candidate.keep,
            drop=candidate.drop,
            summary=summary,
            reason=reason,
            field=candidate.field,
        )

    def _apply_one(self, suggestion: CuratorSuggestion) -> bool:
        if suggestion.scope == "memory":
            if suggestion.kind == "consolidate":
                try:
                    self.memory.add(suggestion.resolution, suggestion.field or "fact")
                except (ValueError, TypeError):
                    return False
                for entry_id in suggestion.targets:
                    try:
                        self.memory.delete(entry_id)
                    except MemoryNotFoundError:
                        pass
                return True
            try:
                self.memory.delete(suggestion.drop)
                return True
            except MemoryNotFoundError:
                return False
        if suggestion.scope == "knowledge":
            if self.knowledge is None:
                return False
            return self.knowledge.delete(suggestion.drop)
        if suggestion.scope == "skill":
            if self.skills is None:
                return False
            try:
                return self.skills.delete_user_skill(suggestion.drop)
            except Exception:
                return False
        profile = self.profile.get()
        items = list(getattr(profile, suggestion.field))
        new_items: list[str] = []
        removed = False
        for item in items:
            if not removed and item == suggestion.drop:
                removed = True
                continue
            new_items.append(item)
        if not removed:
            return False
        preferences = list(profile.preferences)
        goals = list(profile.goals)
        facts = list(profile.facts)
        if suggestion.field == "preferences":
            preferences = new_items
        elif suggestion.field == "goals":
            goals = new_items
        else:
            facts = new_items
        self.profile.replace(profile.name, preferences, goals, profile.style, facts)
        return True

    @staticmethod
    def _summarize(suggestions: list[CuratorSuggestion]) -> str:
        if not suggestions:
            return "审查完成：未发现需要处理的重复或冲突内容"
        counts: dict[str, int] = {}
        for item in suggestions:
            counts[item.scope] = counts.get(item.scope, 0) + 1
        parts = "、".join(
            f"{_SCOPE_LABELS[scope]} {counts[scope]}"
            for scope in ("memory", "profile", "skill", "knowledge")
            if scope in counts
        )
        return f"审查完成：共 {len(suggestions)} 条建议（{parts}）"

    @staticmethod
    def _derive_status(report: CuratorReport) -> str:
        if not report.suggestions:
            return "open"
        if all(item.applied or item.dismissed for item in report.suggestions):
            return "applied" if any(item.applied for item in report.suggestions) else "dismissed"
        return "open"
