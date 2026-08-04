from types import SimpleNamespace

from iris_agent.core.models import Message
from iris_agent.providers.openai_compat import OpenAICompatibleProvider


class FakeCompletions:
    def __init__(self, response):
        self.response = response
        self.kwargs = None

    def create(self, **kwargs):
        self.kwargs = kwargs
        return self.response


def test_provider_converts_text_response():
    message = SimpleNamespace(content="完成", tool_calls=None)
    completions = FakeCompletions(SimpleNamespace(choices=[SimpleNamespace(message=message)]))
    client = SimpleNamespace(chat=SimpleNamespace(completions=completions))
    provider = OpenAICompatibleProvider(client, "model", 0.2)
    result = provider.complete([Message(role="user", content="你好")], [])
    assert result.content == "完成"
    assert completions.kwargs["model"] == "model"


def test_provider_converts_tool_calls():
    call = SimpleNamespace(id="c1", function=SimpleNamespace(name="clock", arguments='{"timezone":"UTC"}'))
    message = SimpleNamespace(content=None, tool_calls=[call])
    client = SimpleNamespace(chat=SimpleNamespace(completions=FakeCompletions(SimpleNamespace(choices=[SimpleNamespace(message=message)]))))
    result = OpenAICompatibleProvider(client, "m").complete([], [])
    assert result.tool_calls[0].arguments == {"timezone": "UTC"}


def test_provider_preserves_malformed_tool_arguments_as_error():
    call = SimpleNamespace(id="c1", function=SimpleNamespace(name="clock", arguments="{"))
    message = SimpleNamespace(content=None, tool_calls=[call])
    client = SimpleNamespace(chat=SimpleNamespace(completions=FakeCompletions(SimpleNamespace(choices=[SimpleNamespace(message=message)]))))
    result = OpenAICompatibleProvider(client, "m").complete([], [])
    assert result.tool_calls[0].argument_error == "invalid_tool_arguments"


def test_tool_message_uses_strict_openai_shape():
    payload = OpenAICompatibleProvider._encode_message(Message(role="tool", content="ok", tool_call_id="c1", name="clock"))
    assert payload == {"role": "tool", "content": "ok", "tool_call_id": "c1"}
