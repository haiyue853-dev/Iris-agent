"""Curator 定时调度：按 cron 周期自动跑审查，发现建议时发站内通知。"""

from __future__ import annotations

import threading
from datetime import datetime

from iris_agent.automation.service import schedule_matches


class CuratorScheduler:
    """轻量进程内调度器：到点跑一次 curator，有建议则发通知。"""

    def __init__(self, curator, notifications=None, schedule: str = "0 3 * * *"):
        self.curator = curator
        self.notifications = notifications
        self.schedule = schedule
        self._last_window: str | None = None
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    def run_pending(self, now: datetime | None = None) -> int:
        moment = now or datetime.now()
        window = moment.strftime("%Y-%m-%dT%H:%M")
        if window == self._last_window:
            return 0
        if not schedule_matches(self.schedule, moment):
            return 0
        self._last_window = window
        report = self.curator.run()
        count = len(report.suggestions)
        if count and self.notifications is not None:
            self.notifications.create(
                "数据审查提醒",
                report.summary,
                report.id,
                tuple(item.id for item in report.suggestions),
            )
        return count

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._loop, name="iris-curator", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=2)

    def _loop(self) -> None:
        while not self._stop.is_set():
            try:
                self.run_pending()
            except Exception:
                pass
            self._stop.wait(60)
