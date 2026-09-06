import json
import time
from collections.abc import Iterator
from concurrent.futures import ThreadPoolExecutor, TimeoutError
from typing import Any

from iris_agent.core.errors import ProviderError
from iris_agent.core.models import Message, ProviderResponse, ToolCall


class OpenAICompatibleProvider:
    def __init__(self, client: Any, model: str, temperature: float = 0.2, first_token_timeout_seconds: float = 20, stream_timeout_seconds: float = 120):
        self.client = client
        self.model = model
        self.temperature = temperature
        self.first_token_timeout_seconds = first_token_timeout_seconds
        self.stream_timeout_seconds = stream_timeout_seconds
        self._closed = False

    def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        close = getattr(self.client, "close", None)
        if callable(close):
            close()

    def complete(self, messages: list[Message], tools: list[dict]) -> ProviderResponse:
        kwargs: dict[str, Any] = {"model": self.model, "temperature": self.temperature, "messages": [self._encode_message(message) for message in messages]}
        if tools:
            kwargs["tools"] = tools
        try:
            response = self.client.chat.completions.create(**kwargs)
            message = response.choices[0].message
            calls = []
            for call in message.tool_calls or []:
                argument_error = None
                try:
                    arguments = json.loads(call.function.arguments or "{}")
                except json.JSONDecodeError:
                    arguments = {}
                    argument_error = "invalid_tool_arguments"
                calls.append(ToolCall(call.id, call.function.name, arguments, argument_error))
            return ProviderResponse(message.content or "", calls)
        except Exception as exc:
            raise ProviderError("模型服务调用失败") from exc

    def stream(self, messages: list[Message], tools: list[dict]) -> Iterator[ProviderResponse]:
        kwargs: dict[str, Any] = {
            "model": self.model,
            "temperature": self.temperature,
            "messages": [self._encode_message(message) for message in messages],
            "stream": True,
        }
        if tools:
            kwargs["tools"] = tools
        yielded_content = [False]
        for attempt in range(2):
            try:
                yield from self._stream_once(kwargs, {}, yielded_content)
                return
            except ProviderError:
                raise
            except Exception as exc:
                if attempt == 0 and not yielded_content[0]:
                    time.sleep(0.4)
                    continue
                raise ProviderError("模型服务调用失败") from exc

    def _bounded_chunks(self, kwargs: dict[str, Any]):
        pool = ThreadPoolExecutor(max_workers=1, thread_name_prefix="iris-model-stream")
        resources: list[Any] = []
        deadline = time.monotonic() + self.stream_timeout_seconds
        first_deadline = time.monotonic() + self.first_token_timeout_seconds
        end = object()

        def open_stream():
            response = self.client.chat.completions.create(**kwargs)
            resources.append(response)
            return iter(response)

        def close_stream():
            for response in resources:
                close = getattr(response, "close", None)
                if callable(close):
                    try:
                        close()
                    except Exception:
                        pass

        pending = pool.submit(open_stream)
        first_chunk = True
        try:
            chunks = pending.result(timeout=max(0, min(first_deadline, deadline) - time.monotonic()))
            while True:
                chunk_deadline = first_deadline if first_chunk else time.monotonic() + self.first_token_timeout_seconds
                pending = pool.submit(next, chunks, end)
                chunk = pending.result(timeout=max(0, min(chunk_deadline, deadline) - time.monotonic()))
                if chunk is end:
                    return
                first_chunk = False
                yield chunk
        except TimeoutError as exc:
            message = "模型首个响应超时，请稍后重试" if first_chunk else "模型流式响应超时，请稍后重试"
            raise ProviderError(message) from exc
        finally:
            # Serialize cleanup after the pending read; never close a generator
            # while it is executing or block timeout delivery on executor exit.
            pool.submit(close_stream)
            pool.shutdown(wait=False)

    def _stream_once(self, kwargs: dict[str, Any], pending_calls: dict[int, dict[str, str]], yielded_content: list[bool]) -> Iterator[ProviderResponse]:
        for chunk in self._bounded_chunks(kwargs):
            if not chunk.choices:
                continue
            delta = chunk.choices[0].delta
            if getattr(delta, "content", None):
                yielded_content[0] = True
                yield ProviderResponse(content=delta.content)
            for call in getattr(delta, "tool_calls", None) or []:
                item = pending_calls.setdefault(call.index, {"id": "", "name": "", "arguments": ""})
                if getattr(call, "id", None):
                    item["id"] = call.id
                function = getattr(call, "function", None)
                if function is not None:
                    if getattr(function, "name", None):
                        item["name"] = function.name
                    if getattr(function, "arguments", None):
                        item["arguments"] += function.arguments
        calls = []
        for item in pending_calls.values():
            argument_error = None
            try:
                arguments = json.loads(item["arguments"] or "{}")
            except json.JSONDecodeError:
                arguments = {}
                argument_error = "invalid_tool_arguments"
            calls.append(ToolCall(item["id"], item["name"], arguments, argument_error))
        if calls:
            yield ProviderResponse(tool_calls=calls)

    @staticmethod
    def _encode_message(message: Message) -> dict[str, Any]:
        content: Any = message.model_content
        if message.image_urls:
            content = [{"type": "text", "text": message.model_content}, *[{"type": "image_url", "image_url": {"url": url}} for url in message.image_urls]]
        data: dict[str, Any] = {"role": message.role, "content": content}
        if message.tool_calls:
            data["tool_calls"] = [{"id": call.id, "type": "function", "function": {"name": call.name, "arguments": json.dumps(call.arguments, ensure_ascii=False)}} for call in message.tool_calls]
        if message.tool_call_id:
            data["tool_call_id"] = message.tool_call_id
        if message.name and message.role != "tool":
            data["name"] = message.name
        return data
