from iris_agent.context_compression.compressor import ContextCompressor
from iris_agent.core.models import Message, ProviderResponse, ToolCall


class Provider:
    def complete(self, messages, tools):
        return ProviderResponse(content="摘要")


def test_compression_keeps_tool_call_and_result_together():
    messages = [
        Message(role="user", content="旧问题"),
        Message(role="assistant", tool_calls=[ToolCall("call-1", "read_file", {})]),
        Message(role="tool", content="result", tool_call_id="call-1", name="read_file"),
        Message(role="assistant", content="旧回答"),
        Message(role="user", content="新问题"),
        Message(role="assistant", content="新回答"),
    ]
    compressor = ContextCompressor(Provider(), keep_recent=4)

    compressed = compressor.compress(messages)

    retained_ids = {message.tool_call_id for message in compressed if message.role == "tool"}
    call_ids = {call.id for message in compressed for call in message.tool_calls}
    assert retained_ids == call_ids


def test_compression_can_use_token_threshold():
    compressor = ContextCompressor(Provider(), trigger_chars=10_000, trigger_tokens=5)

    assert compressor.needs_compression([Message(role="user", content="123456789012345678901234")])

