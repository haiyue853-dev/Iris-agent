"""Filesystem persistence for raw journals, curated Markdown and task state."""

from __future__ import annotations

from dataclasses import replace
from datetime import datetime
import json
from pathlib import Path
import re
import threading
from uuid import uuid4

from iris_agent.personal_assistant.models import ArchiveRecord, MessageClassification, PersonalTask, TaskDraft


_CATEGORIES = frozenset({"工作", "学习", "生活", "灵感", "其他"})


class PersonalAssistantRepository:
    def __init__(self, root: Path):
        self.root = Path(root)
        self.raw_root = self.root / "raw"
        self.archive_root = self.root / "archive"
        self.task_root = self.root / "tasks"
        self.index_root = self.root / "index"
        self.index_path = self.index_root / "archive.json"
        self.task_path = self.task_root / "tasks.json"
        self.pending_path = self.task_root / "pending.json"
        self._lock = threading.RLock()
        for path in (self.raw_root, self.archive_root, self.task_root, self.index_root):
            path.mkdir(parents=True, exist_ok=True)
        for category in _CATEGORIES:
            (self.archive_root / category).mkdir(parents=True, exist_ok=True)

    @staticmethod
    def _load(path: Path, fallback: dict) -> dict:
        if not path.exists():
            return dict(fallback)
        try:
            value = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return dict(fallback)
        return value if isinstance(value, dict) else dict(fallback)

    @staticmethod
    def _save(path: Path, value: dict) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_name(f".{path.name}.{uuid4().hex}.tmp")
        temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")
        temporary.replace(path)

    def save_raw(self, *, platform: str, user_id: str, message_id: str, text: str, created_at: datetime) -> bool:
        key = f"{platform}:{user_id}:{message_id}"
        with self._lock:
            index = self._load(self.index_path, {"seen_messages": {}, "archives": []})
            seen = index.setdefault("seen_messages", {})
            if key in seen:
                return False
            journal = self.raw_root / created_at.strftime("%Y") / created_at.strftime("%m") / f"{created_at:%Y-%m-%d}.md"
            journal.parent.mkdir(parents=True, exist_ok=True)
            if not journal.exists():
                journal.write_text(f"# QQ 原始消息 {created_at:%Y-%m-%d}\n\n", encoding="utf-8")
            block = (
                f"<!-- message:{key} -->\n"
                f"## {created_at.isoformat()} · {platform}:{user_id}\n\n"
                f"{text.rstrip()}\n\n"
            )
            with journal.open("a", encoding="utf-8") as stream:
                stream.write(block)
            seen[key] = {"created_at": created_at.isoformat(), "journal": str(journal.relative_to(self.root))}
            self._save(self.index_path, index)
            return True

    def save_archive(
        self,
        classification: MessageClassification,
        *,
        source_message_id: str,
        source_user_id: str,
        original_text: str,
        created_at: datetime,
    ) -> ArchiveRecord:
        category = classification.category if classification.category in _CATEGORIES else "其他"
        title = classification.title.strip()[:100] or "未命名资料"
        summary = classification.summary.strip()[:1000]
        tags = tuple(dict.fromkeys(tag.strip()[:30] for tag in classification.tags if tag.strip()))[:12]
        record_id = f"archive_{uuid4().hex}"
        slug = re.sub(r'[<>:"/\\|?*\x00-\x1f]+', "-", title).strip(" .-")[:50] or "item"
        path = self.archive_root / category / f"{created_at:%Y-%m-%d}-{record_id[-8:]}-{slug}.md"
        tags_json = json.dumps(list(tags), ensure_ascii=False)
        content = (
            "---\n"
            f"id: {record_id}\n"
            f"category: {category}\n"
            f"tags: {tags_json}\n"
            f"created_at: {created_at.isoformat()}\n"
            f"source_message_id: {json.dumps(source_message_id, ensure_ascii=False)}\n"
            "---\n\n"
            f"# {title}\n\n"
            f"## 摘要\n\n{summary or '无'}\n\n"
            f"## 原文\n\n{original_text.rstrip()}\n"
        )
        with self._lock:
            path.write_text(content, encoding="utf-8")
            record = ArchiveRecord(
                id=record_id,
                title=title,
                summary=summary,
                category=category,
                tags=tags,
                source_message_id=source_message_id,
                source_user_id=source_user_id,
                created_at=created_at,
                path=str(path),
                original_text=original_text,
            )
            index = self._load(self.index_path, {"seen_messages": {}, "archives": []})
            index.setdefault("archives", []).append(record.to_dict())
            self._save(self.index_path, index)
            return record

    def archives(self) -> list[ArchiveRecord]:
        with self._lock:
            index = self._load(self.index_path, {"seen_messages": {}, "archives": []})
            return [ArchiveRecord.from_dict(item) for item in index.get("archives", []) if isinstance(item, dict)]

    def search(self, query: str, *, user_id: str | None = None, limit: int = 5) -> list[ArchiveRecord]:
        words = [word.lower() for word in re.findall(r"[\w\u4e00-\u9fff]+", query) if word.strip()]
        scored: list[tuple[int, ArchiveRecord]] = []
        for record in self.archives():
            if user_id is not None and record.source_user_id != user_id:
                continue
            haystack = " ".join((record.title, record.summary, " ".join(record.tags), record.original_text)).lower()
            score = sum(4 if word in record.title.lower() else 1 for word in words if word in haystack)
            if score:
                scored.append((score, record))
        scored.sort(key=lambda item: (item[0], item[1].created_at), reverse=True)
        return [record for _, record in scored[:limit]]

    def _task_ledger(self) -> dict:
        return self._load(self.task_path, {"next_id": 1, "tasks": []})

    def tasks(self) -> list[PersonalTask]:
        with self._lock:
            ledger = self._task_ledger()
            return [PersonalTask.from_dict(item) for item in ledger.get("tasks", []) if isinstance(item, dict)]

    def create_task(
        self,
        draft: TaskDraft,
        *,
        user_id: str,
        platform: str,
        source_message_id: str,
        source_text: str,
        created_at: datetime,
        due_at: datetime,
    ) -> PersonalTask:
        with self._lock:
            ledger = self._task_ledger()
            number = int(ledger.get("next_id", 1))
            task = PersonalTask(
                short_id=f"T-{number:03d}",
                title=draft.title.strip()[:200],
                user_id=user_id,
                platform=platform,
                source_message_id=source_message_id,
                source_text=source_text,
                time_kind=draft.time_kind,
                status="active",
                created_at=created_at,
                updated_at=created_at,
                due_at=due_at,
                next_remind_at=due_at,
            )
            ledger["next_id"] = number + 1
            ledger.setdefault("tasks", []).append(task.to_dict())
            self._save(self.task_path, ledger)
            return task

    def replace_task(self, task: PersonalTask) -> PersonalTask:
        with self._lock:
            ledger = self._task_ledger()
            items = ledger.setdefault("tasks", [])
            for index, item in enumerate(items):
                if str(item.get("short_id")) == task.short_id:
                    items[index] = task.to_dict()
                    self._save(self.task_path, ledger)
                    return task
            raise KeyError(task.short_id)

    def find_task(self, short_id: str, user_id: str) -> PersonalTask | None:
        normalized = short_id.upper()
        return next((task for task in self.tasks() if task.short_id == normalized and task.user_id == user_id), None)

    def latest_active_task(self, user_id: str) -> PersonalTask | None:
        active = [task for task in self.tasks() if task.user_id == user_id and task.status == "active"]
        if not active:
            return None
        return max(active, key=lambda task: (task.last_reminded_at or task.created_at, task.created_at))

    def save_pending(self, user_id: str, draft: TaskDraft, source_message_id: str, source_text: str, *, platform: str = "qq") -> None:
        with self._lock:
            pending = self._load(self.pending_path, {})
            pending[user_id] = {
                "draft": draft.to_dict(),
                "source_message_id": source_message_id,
                "source_text": source_text,
                "platform": platform,
            }
            self._save(self.pending_path, pending)

    def pop_pending(self, user_id: str) -> tuple[TaskDraft, str, str, str] | None:
        with self._lock:
            pending = self._load(self.pending_path, {})
            value = pending.pop(user_id, None)
            if value is None:
                return None
            self._save(self.pending_path, pending)
            return (
                TaskDraft.from_dict(value["draft"]),
                str(value["source_message_id"]),
                str(value["source_text"]),
                str(value.get("platform", "qq")),
            )

    def clear_pending(self, user_id: str) -> bool:
        with self._lock:
            pending = self._load(self.pending_path, {})
            existed = pending.pop(user_id, None) is not None
            if existed:
                self._save(self.pending_path, pending)
            return existed
