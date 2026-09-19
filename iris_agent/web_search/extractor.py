"""Small bounded page batches; a stalled page never blocks the batch return."""
from contextvars import copy_context
from queue import Empty, Queue
from threading import BoundedSemaphore, Event, Thread
from time import monotonic

import httpx

from iris_agent.tools.base import ToolInvocationError
from iris_agent.tools.context import remaining, report_progress
from iris_agent.web_search.fetcher import UnsafeUrlError, PageTooLargeError


class PageExtractor:
    def __init__(self, fetcher, max_workers=3):
        self.fetcher = fetcher
        self.timeout = fetcher.timeout
        self._slots = BoundedSemaphore(max_workers)
        self.max_workers = max_workers

    def extract_many(self, urls):
        if not 1 <= len(urls) <= 5:
            raise ToolInvocationError("invalid_tool_arguments", "每次提取 1 到 5 个 URL")
        started = monotonic()
        deadline = started + self.timeout
        tasks, completed = Queue(), Queue()
        stop = Event()
        for index, url in enumerate(urls):
            tasks.put((index, url))

        def work():
            try:
                while not stop.is_set():
                    try:
                        index, url = tasks.get_nowait()
                    except Empty:
                        break
                    page_started = monotonic()
                    try:
                        remaining(deadline)
                        result = self.fetcher.extract(url, deadline=deadline)
                    except Exception as exc:
                        if isinstance(exc, ToolInvocationError):
                            code, message = exc.code, str(exc)
                        elif isinstance(exc, UnsafeUrlError):
                            code, message = "unsafe_url", "链接未通过公网地址检查"
                        elif isinstance(exc, PageTooLargeError):
                            code, message = "page_too_large", "页面超过下载大小限制"
                        elif isinstance(exc, httpx.TimeoutException):
                            code, message = "tool_timeout", "页面请求超时"
                        elif isinstance(exc, httpx.HTTPStatusError):
                            code, message = "page_http_error", f"页面返回 HTTP {exc.response.status_code}"
                        else:
                            code, message = "page_extract_failed", "页面提取失败"
                        result = {"url": url, "ok": False, "error_code": code, "error_message": message,
                                  "duration_ms": round((monotonic() - page_started) * 1000)}
                    completed.put((index, result))
            finally:
                self._slots.release()

        workers = 0
        for _ in range(min(self.max_workers, len(urls))):
            if not self._slots.acquire(blocking=False):
                break
            context = copy_context()
            try:
                Thread(target=lambda context=context: context.run(work), daemon=True, name="iris-web-extract").start()
            except BaseException:
                self._slots.release()
                stop.set()
                raise
            workers += 1
        results = {}
        reason = "tool_executor_busy" if workers == 0 else "tool_timeout"
        try:
            while workers and len(results) < len(urls):
                try:
                    seconds = remaining(deadline)
                    index, result = completed.get(timeout=min(.05, seconds))
                except Empty:
                    continue
                except ToolInvocationError as exc:
                    reason = exc.code
                    break
                results[index] = result
                report_progress(phase="extracting", completed=len(results), total=len(urls), url=result["url"])
        finally:
            stop.set()
        # Include pages completed at the deadline, without waiting for blocked workers.
        while True:
            try:
                index, result = completed.get_nowait()
                results[index] = result
            except Empty:
                break
        pages = [results.get(index, {"url": url, "ok": False, "error_code": reason,
                                    "error_message": "提取资源忙" if reason == "tool_executor_busy" else "页面提取已超时或取消"})
                 for index, url in enumerate(urls)]
        successful = sum(page["ok"] for page in pages)
        return {"pages": pages, "successful": successful, "failed": len(pages) - successful,
                "duration_ms": round((monotonic() - started) * 1000)}
