from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from uuid import uuid4


@dataclass(frozen=True, slots=True)
class Notification:
    id: str
    title: str
    summary: str
    task_id: str
    item_ids: tuple[str, ...]
    read: bool = False


class NotificationService:
    def __init__(self, root: Path):
        self.root = root
        self.root.mkdir(parents=True, exist_ok=True)
        self.path = root / "notifications.json"

    def _read(self) -> dict[str, list[dict[str, object]]]:
        if not self.path.exists():
            return {"notifications": []}
        return json.loads(self.path.read_text(encoding="utf-8"))

    def _write(self, data: dict[str, list[dict[str, object]]]) -> None:
        temporary = self.path.with_suffix(".tmp")
        temporary.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
        temporary.replace(self.path)

    def list_notifications(self) -> list[Notification]:
        notifications = [
            Notification(**{**raw, "item_ids": tuple(raw["item_ids"])})
            for raw in self._read()["notifications"]
        ]
        return sorted(notifications, key=lambda item: (item.read, item.id), reverse=False)

    def create(self, title: str, summary: str, task_id: str, item_ids: tuple[str, ...]) -> Notification:
        notification = Notification(uuid4().hex, title, summary, task_id, item_ids)
        data = self._read()
        data["notifications"].append({
            "id": notification.id, "title": notification.title, "summary": notification.summary,
            "task_id": notification.task_id, "item_ids": list(notification.item_ids), "read": notification.read,
        })
        self._write(data)
        return notification

    def mark_read(self, notification_id: str) -> Notification:
        data = self._read()
        for item in data["notifications"]:
            if item["id"] == notification_id:
                item["read"] = True
                self._write(data)
                return Notification(**{**item, "item_ids": tuple(item["item_ids"])})
        raise KeyError(notification_id)

    def delete(self, notification_id: str) -> None:
        data = self._read()
        remaining = [item for item in data["notifications"] if item["id"] != notification_id]
        if len(remaining) == len(data["notifications"]):
            raise KeyError(notification_id)
        data["notifications"] = remaining
        self._write(data)
