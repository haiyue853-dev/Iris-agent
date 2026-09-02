import json
import time
from collections.abc import Iterator
from concurrent.futures import ThreadPoolExecutor, TimeoutError
from itertools import chain
from typing import Any

from iris_agent.core.errors import ProviderError
from iris_agent.core.models import Message, ProviderResponse, ToolCall


class OpenAICompatibleProvider:
    def __init__(self, client: Any, model: str, temperature: float = 0.2, first_token_timeout_seconds: float = 20):
        self.client = client
        self.model = model
        self.temperature = temperature
        self.first_token_timeout_seconds = first_token_timeout_seconds
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

    def _stream_once(self, kwargs: dict[str, Any], pending_calls: dict[int, dict[str, str]], yielded_content: list[bool]) -> Iterator[ProviderResponse]:
        chunks = iter(self.client.chat.completions.create(**kwargs))
        pool = ThreadPoolExecutor(max_workers=1)
        first = pool.submit(next, chunks)
        try:
            first_chunk = first.result(timeout=self.first_token_timeout_seconds)
        except TimeoutError as exc:
            pool.shutdown(wait=False, cancel_futures=True)
            raise ProviderError("模型首个响应超时，请稍后重试") from exc
        finally:
            if first.done():
                pool.shutdown(wait=False)
        for chunk in chain((first_chunk,), chunks):
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
