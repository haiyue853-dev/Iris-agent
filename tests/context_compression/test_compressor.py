import pytest

from iris_agent.context_compression.compressor import ContextCompressor
from iris_agent.core.models import Message, ProviderResponse


class FakeProvider:
    def __init__(self, content: str):
        self.content = content
        self.last_messages = None

    def complete(self, messages, tools):
        self.last_messages = messages
        return ProviderResponse(content=self.content, tool_calls=[])


class RaisingProvider:
    def complete(self, messages, tools):
        raise RuntimeError("provider down")


def _msg(role: str, content: str, name: str | None = None) -> Message:
    return Message(role=role, content=content, name=name)


def test_needs_compression_when_over_threshold():
    compressor = ContextCompressor(FakeProvider("摘要"), trigger_chars=10, keep_recent=2)

    assert compressor.needs_compression([_msg("user", "这是一条超过阈值的内容")]) is True


def test_needs_compression_false_when_under_threshold():
    compressor = ContextCompressor(FakeProvider("摘要"), trigger_chars=1000, keep_recent=2)

    assert compressor.needs_compression([_msg("user", "短")]) is False


def test_needs_compression_false_when_disabled():
    compressor = ContextCompressor(FakeProvider("摘要"), trigger_chars=1, enabled=False)

    assert compressor.needs_compression([_msg("user", "很长很长很长")]) is False


def test_compress_keeps_recent_and_summarizes():
    provider = FakeProvider("早期对话摘要")
    compressor = ContextCompressor(provider, trigger_chars=1000, keep_recent=2)
    messages = [_msg("user", "u1"), _msg("assistant", "a1"), _msg("user", "u2"), _msg("assistant", "a2")]

    result = compressor.compress(messages)

    assert len(result) == 3
    assert result[0].role == "system"
    assert result[0].content == "[对话摘要] 早期对话摘要"
    assert result[1].content == "u2"
    assert result[2].content == "a2"


def test_compress_is_idempotent_single_summary():
    provider = FakeProvider("新摘要")
    compressor = ContextCompressor(provider, trigger_chars=1000, keep_recent=2)
    messages = [_msg("system", "[对话摘要] 旧摘要"), _msg("user", "u1"), _msg("assistant", "a1"), _msg("user", "u2")]

    result = compressor.compress(messages)

    summaries = [m for m in result if m.role == "system" and m.content.startswith("[对话摘要]")]
    assert len(summaries) == 1


def test_compress_returns_original_on_summary_failure():
    compressor = ContextCompressor(RaisingProvider(), trigger_chars=1000, keep_recent=2)
    messages = [_msg("user", "u1"), _msg("assistant", "a1"), _msg("user", "u2"), _msg("assistant", "a2")]

    result = compressor.compress(messages)

    assert result == messages


def test_compress_noop_when_few_messages():
    compressor = ContextCompressor(FakeProvider("摘要"), keep_recent=10)
    messages = [_msg("user", "u1"), _msg("assistant", "a1")]

    assert compressor.compress(messages) == messages


def test_compress_strips_tool_content_from_summary_input():
    provider = FakeProvider("摘要")
    compressor = ContextCompressor(provider, keep_recent=1)
    messages = [
        _msg("user", "查一下密钥"),
        Message(role="tool", content='{"secret": "topkey"}', name="read_file", tool_call_id="c1"),
        _msg("assistant", "查完了"),
    ]

    compressor.compress(messages)

    text = provider.last_messages[1].content
    assert "topkey" not in text
    assert "read_file" in text


def test_summary_keeps_tool_arguments_results_and_errors():
    from iris_agent.core.models import ToolCall
    messages = [
        Message(role='assistant', tool_calls=[ToolCall('c', 'lookup', {'query': 'release date'})]),
        Message(role='tool', name='lookup', tool_call_id='c', content='{"date":"2026-09-06","api_key":"hidden"}'),
        Message(role='tool', name='command', content='{"error":"exit_1","message":"compile failed"}'),
    ]
    text = ContextCompressor._serialize(messages)
    assert 'release date' in text
    assert '2026-09-06' in text
    assert 'compile failed' in text
    assert 'hidden' not in text


def test_compression_counts_large_tool_arguments_and_non_ascii_text():
    from iris_agent.core.models import ToolCall
    compressor = ContextCompressor(FakeProvider('summary'), trigger_tokens=100)
    assert compressor.needs_compression([Message(role='assistant', tool_calls=[ToolCall('c', 'write', {'text': 'x' * 2000})])])
    assert compressor.needs_compression([Message(role='user', content='中文' * 100)])
