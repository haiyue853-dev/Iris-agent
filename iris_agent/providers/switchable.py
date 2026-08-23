from __future__ import annotations

import threading
import weakref
import logging
from contextlib import contextmanager
from dataclasses import dataclass
from typing import Iterator

from iris_agent.providers.base import ModelProvider

logger = logging.getLogger(__name__)


@dataclass(eq=False, slots=True)
class _ProviderEntry:
    provider: ModelProvider
    closing: bool = False
    closed: bool = False


class SwitchableProvider:
    """Thread-safe provider handle with lease-aware retirement."""

    def __init__(self, provider: ModelProvider):
        self._require_weakrefable(provider)
        self._current = _ProviderEntry(provider)
        self._lock = threading.RLock()
        self._condition = threading.Condition(self._lock)
        self._disposer_state = threading.local()
        self._active: dict[_ProviderEntry, int] = {}
        self._retired: set[_ProviderEntry] = set()
        self._closing: set[_ProviderEntry] = set()
        self._closed_providers: list[weakref.ReferenceType[ModelProvider]] = []
        self._closed = False

    def current(self) -> ModelProvider:
        with self._lock:
            return self._current.provider

    @contextmanager
    def lease(self) -> Iterator[ModelProvider]:
        with self._lock:
            if self._closed:
                raise RuntimeError("Provider handle is closed")
            entry = self._current
            self._active[entry] = self._active.get(entry, 0) + 1
        try:
            yield entry.provider
        finally:
            close_target = None
            with self._lock:
                remaining = self._active[entry] - 1
                if remaining:
                    self._active[entry] = remaining
                else:
                    self._active.pop(entry, None)
                    if entry in self._retired:
                        self._retired.remove(entry)
                        self._mark_closing_locked(entry)
                        close_target = entry
            if close_target is not None:
                self._dispose(close_target)

    def replace(self, provider: ModelProvider) -> None:
        self._reject_disposer_reentry()
        self._require_weakrefable(provider)
        close_target = None
        with self._lock:
            while True:
                if self._was_closed_locked(provider):
                    raise RuntimeError("Provider is already closed")
                if any(entry.provider is provider for entry in self._closing):
                    self._condition.wait()
                    continue
                break
            if self._closed:
                close_target = _ProviderEntry(provider)
                self._mark_closing_locked(close_target)
                error = RuntimeError("Provider handle is closed")
            else:
                old = self._current
                if old.provider is provider:
                    return
                restored = next(
                    (entry for entry in self._retired if entry.provider is provider),
                    None,
                )
                if restored is None:
                    restored = _ProviderEntry(provider)
                else:
                    self._retired.remove(restored)
                self._current = restored
                if self._active.get(old):
                    self._retired.add(old)
                else:
                    self._mark_closing_locked(old)
                    close_target = old
                error = None
        if close_target is not None:
            self._dispose(close_target)
        if error is not None:
            raise error

    def complete(self, messages, tools):
        with self.lease() as provider:
            return provider.complete(messages, tools)

    def stream(self, messages, tools):
        with self.lease() as provider:
            stream = getattr(provider, "stream", None)
            if callable(stream):
                yield from stream(messages, tools)
            else:
                yield provider.complete(messages, tools)

    def close(self) -> None:
        self._reject_disposer_reentry()
        targets = []
        with self._lock:
            if self._closed:
                return
            self._closed = True
            current = self._current
            if self._active.get(current):
                self._retired.add(current)
            else:
                self._mark_closing_locked(current)
                targets.append(current)
            for entry in tuple(self._retired):
                if not self._active.get(entry):
                    self._retired.remove(entry)
                    self._mark_closing_locked(entry)
                    targets.append(entry)
        for entry in targets:
            self._dispose(entry)

    def _mark_closing_locked(self, entry: _ProviderEntry) -> None:
        if entry.closing or entry.closed:
            return
        entry.closing = True
        self._closing.add(entry)

    def _dispose(self, entry: _ProviderEntry) -> None:
        self._disposer_state.active = True
        try:
            close = getattr(entry.provider, "close", None)
            if callable(close):
                try:
                    close()
                except Exception:
                    logger.warning("Provider close failed")
        finally:
            self._disposer_state.active = False
            with self._lock:
                entry.closing = False
                entry.closed = True
                self._closing.discard(entry)
                self._remember_closed_locked(entry.provider)
                self._condition.notify_all()

    def _remember_closed_locked(self, provider: ModelProvider) -> None:
        self_ref = weakref.ref(self)

        def discard(reference: weakref.ReferenceType[ModelProvider]) -> None:
            handle = self_ref()
            if handle is not None:
                with handle._lock:
                    if reference in handle._closed_providers:
                        handle._closed_providers.remove(reference)

        self._closed_providers.append(weakref.ref(provider, discard))

    def _was_closed_locked(self, provider: ModelProvider) -> bool:
        return any(reference() is provider for reference in self._closed_providers)

    def _reject_disposer_reentry(self) -> None:
        if getattr(self._disposer_state, "active", False):
            raise RuntimeError("Provider disposal cannot mutate its handle")

    @staticmethod
    def _require_weakrefable(provider: ModelProvider) -> None:
        try:
            weakref.ref(provider)
        except TypeError as exc:
            raise TypeError("Provider must support weak references") from exc
