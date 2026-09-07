"""Bounded, cancellable waiting around synchronous and streaming tools."""

from contextvars import copy_context
from queue import Empty, Full, Queue
import threading
from time import monotonic

from iris_agent.core.models import AgentEvent
from iris_agent.tools.base import ToolExecutionResult, ToolInvocationError


class ToolExecutor:
    def __init__(self, timeout_seconds: float = 120, max_workers: int = 8):
        if timeout_seconds <= 0 or max_workers < 1:
            raise ValueError('Tool execution limits must be positive')
        self.timeout_seconds = timeout_seconds
        self._slots = threading.BoundedSemaphore(max_workers)

    def execute(self, call, registry, cancelled):
        started = monotonic()
        deadline = started + self.timeout_seconds
        acquired = False
        while not cancelled() and monotonic() < deadline:
            if self._slots.acquire(timeout=min(.05, max(0, deadline - monotonic()))):
                acquired = True
                break
        if cancelled():
            if acquired:
                self._slots.release()
            return
        if not acquired or monotonic() >= deadline:
            if acquired:
                self._slots.release()
            yield self._finished(call, ToolExecutionResult(False, error_code='tool_executor_busy', error_message='工具执行资源忙，请稍后重试'), started)
            return

        stopped, done = threading.Event(), threading.Event()
        progress = Queue(maxsize=32)
        state = {'execution': None, 'cancel_sent': False, 'result': None}
        lock = threading.Lock()

        def stop_execution():
            stopped.set()
            with lock:
                execution = state['execution']
                cancel = getattr(execution, 'cancel', None)
                if not callable(cancel) or state['cancel_sent']:
                    return
                state['cancel_sent'] = True
            try:
                cancel()
            except Exception:
                pass

        def work():
            try:
                if stopped.is_set():
                    return
                result = registry.invoke(call.name, call.arguments)
                stream = getattr(result.value, 'stream', None) if result.ok else None
                if callable(stream):
                    with lock:
                        state['execution'] = result.value
                    if stopped.is_set():
                        stop_execution()
                        return
                    iterator = iter(stream())
                    try:
                        for item in iterator:
                            while not stopped.is_set():
                                try:
                                    progress.put(dict(item), timeout=.05)
                                    break
                                except Full:
                                    continue
                            if stopped.is_set():
                                break
                    finally:
                        close = getattr(iterator, 'close', None)
                        if callable(close):
                            close()
                    result = ToolExecutionResult(True, value=getattr(result.value, 'result', None))
                state['result'] = result
            except ToolInvocationError as exc:
                state['result'] = ToolExecutionResult(False, error_code=exc.code, error_message=str(exc))
            except Exception as exc:
                state['result'] = ToolExecutionResult(False, error_code='tool_execution_error', error_message=str(exc))
            finally:
                done.set()
                self._slots.release()

        context = copy_context()
        worker = threading.Thread(target=lambda: context.run(work), name='iris-tool', daemon=True)
        try:
            worker.start()
        except BaseException:
            self._slots.release()
            raise
        try:
            while True:
                if cancelled():
                    stop_execution()
                    return
                if done.is_set() and progress.empty():
                    yield self._finished(call, state['result'], started)
                    return
                if monotonic() >= deadline:
                    stop_execution()
                    result = ToolExecutionResult(False, error_code='tool_timeout', error_message='工具执行超时；已请求取消，不支持中断的操作可能仍在结束中，请勿自动重复执行写入操作。')
                    yield self._finished(call, result, started)
                    return
                try:
                    item = progress.get(timeout=min(.05, max(0, deadline - monotonic())))
                except Empty:
                    continue
                if not cancelled():
                    yield AgentEvent('tool_progress', {**item, 'call_id': call.id, 'name': call.name})
        finally:
            if not done.is_set():
                stop_execution()

    @staticmethod
    def _finished(call, result, started):
        data = {'call_id': call.id, 'name': call.name, 'ok': result.ok, 'duration_ms': round((monotonic() - started) * 1000)}
        if result.ok:
            data['result'] = result.value
        else:
            data.update(error_code=result.error_code, error_message=result.error_message)
        return AgentEvent('tool_finished', data)


DEFAULT_EXECUTOR = ToolExecutor()
