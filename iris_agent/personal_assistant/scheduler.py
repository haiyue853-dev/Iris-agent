"""Background delivery of persistent personal reminders."""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime, timedelta
import threading

from iris_agent.personal_assistant.service import PersonalAssistantService


class PersonalReminderScheduler:
    def __init__(
        self,
        service: PersonalAssistantService,
        push: Callable[[str, str, str], bool],
        *,
        poll_seconds: float = 15,
        failed_retry_minutes: int = 5,
    ) -> None:
        self.service = service
        self.push = push
        self.poll_seconds = poll_seconds
        self.failed_retry = timedelta(minutes=failed_retry_minutes)
        self._retry_after: dict[str, datetime] = {}
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    def run_pending(self, now: datetime | None = None) -> int:
        moment = self.service._moment(now)
        delivered = 0
        for task in self.service.due_tasks(moment):
            if self._retry_after.get(task.short_id, moment) > moment:
                continue
            if self.push(task.platform, task.user_id, self.service.reminder_text(task)):
                self.service.mark_notified(task.short_id, moment)
                self._retry_after.pop(task.short_id, None)
                delivered += 1
            else:
                self._retry_after[task.short_id] = moment + self.failed_retry
        return delivered

    def start(self) -> None:
        if self._thread is not None and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._loop, name="iris-personal-reminders", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=2)

    def _loop(self) -> None:
        while not self._stop.is_set():
            self.run_pending()
            self._stop.wait(self.poll_seconds)
