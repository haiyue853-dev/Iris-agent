import json
from typing import Any

from iris_agent.core.errors import ProviderError
from iris_agent.core.models import Message, ProviderResponse, ToolCall


class OpenAICompatibleProvider:
    def __init__(self, client: Any, model: str, temperature: float = 0.2):
        self.client = client
        self.model = model
        self.temperature = temperature

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
            status_code = getattr(exc, "status_code", None)
            detail = type(exc).__name__
            if status_code is not None:
                detail = f"{detail}, HTTP {status_code}"
            raise ProviderError(f"模型服务调用失败（{detail}）") from exc

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
