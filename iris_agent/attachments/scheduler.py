from __future__ import annotations

from threading import Event, Lock, Thread

from .service import AttachmentService


class AttachmentCleanupScheduler:
    def __init__(self, service: AttachmentService, interval_seconds: int):
        if interval_seconds < 1:
            raise ValueError("cleanup interval must be positive")
        self._service = service
        self._interval_seconds = interval_seconds
        self._stop = Event()
        self._lock = Lock()
        self._thread: Thread | None = None

    def start(self) -> None:
        with self._lock:
            if self._thread is not None:
                return
            self._service.cleanup_expired()
            self._stop.clear()
            self._thread = Thread(target=self._run, name="attachment-cleanup", daemon=True)
            self._thread.start()

    def stop(self) -> None:
        with self._lock:
            thread = self._thread
            self._thread = None
            self._stop.set()
        if thread is not None:
            thread.join(timeout=2)

    def _run(self) -> None:
        while not self._stop.wait(self._interval_seconds):
            self._service.cleanup_expired()
