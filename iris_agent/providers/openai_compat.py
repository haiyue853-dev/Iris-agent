import json
from collections.abc import Iterator
from typing import Any

from iris_agent.core.errors import ProviderError
from iris_agent.core.models import Message, ProviderResponse, ToolCall


class OpenAICompatibleProvider:
    def __init__(self, client: Any, model: str, temperature: float = 0.2):
        self.client = client
        self.model = model
        self.temperature = temperature
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
        pending_calls: dict[int, dict[str, str]] = {}
        try:
            chunks = self.client.chat.completions.create(**kwargs)
            for chunk in chunks:
                if not chunk.choices:
                    continue
                delta = chunk.choices[0].delta
                if getattr(delta, "content", None):
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
        except Exception as exc:
            raise ProviderError("模型服务调用失败") from exc

    @staticmethod
    def _encode_message(message: Message) -> dict[str, Any]:
        data: dict[str, Any] = {"role": message.role, "content": message.content}
        if message.tool_calls:
            data["tool_calls"] = [{"id": call.id, "type": "function", "function": {"name": call.name, "arguments": json.dumps(call.arguments, ensure_ascii=False)}} for call in message.tool_calls]
        if message.tool_call_id:
            data["tool_call_id"] = message.tool_call_id
        if message.name and message.role != "tool":
            data["name"] = message.name
        return data
