from threading import Event, RLock


class ChatCancellationRegistry:
    """Thread-safe cancellation signals for active direct chat executions."""

    def __init__(self) -> None:
        self._lock = RLock()
        self._signals: dict[str, Event] = {}

    def register(self, task_id: str) -> Event:
        signal = Event()
        with self._lock:
            self._signals[task_id] = signal
        return signal

    def cancel(self, task_id: str) -> bool:
        with self._lock:
            signal = self._signals.get(task_id)
            if signal is None:
                return False
            signal.set()
            return True

    def signal(self, task_id: str) -> Event | None:
        with self._lock:
            return self._signals.get(task_id)

    def unregister(self, task_id: str) -> None:
        with self._lock:
            self._signals.pop(task_id, None)
