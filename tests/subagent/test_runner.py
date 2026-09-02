from iris_agent.core.models import Message, ProviderResponse, ToolCall
from iris_agent.subagent.models import SubagentRequest
from iris_agent.subagent.runner import SubagentRunner
from iris_agent.tools.base import Tool
from iris_agent.tools.registry import ToolRegistry


class FakeProvider:
    def __init__(self, responses: list[ProviderResponse]):
        self.responses = list(responses)
        self.seen_messages: list[list[Message]] = []
        self.seen_tools: list[list[dict]] = []

    def complete(self, messages: list[Message], tools: list[dict]) -> ProviderResponse:
        self.seen_messages.append(messages)
        self.seen_tools.append(tools)
        return self.responses.pop(0)


def _registry() -> ToolRegistry:
    registry = ToolRegistry()
    registry.register(Tool("read_file", "读文件", {"type": "object", "properties": {}}, lambda: "ok"))
    registry.register(Tool("remember", "写记忆", {"type": "object", "properties": {}}, lambda: None))
    registry.register(Tool("web_search", "联网搜索", {"type": "object", "properties": {}}, lambda: []))
    registry.register(Tool("fetch_page", "抓取网页", {"type": "object", "properties": {}}, lambda: ""))
    return registry


def _runner(provider, **kwargs) -> SubagentRunner:
    defaults = dict(
        provider=provider,
        tool_subset=_registry().subset,
        system_prompt="你是子代理",
        default_allowed_tools=["read_file"],
    )
    defaults.update(kwargs)
    return SubagentRunner(**defaults)


def test_returns_final_text_without_tools():
    provider = FakeProvider([ProviderResponse(content="分析结论", tool_calls=[])])
    runner = _runner(provider)

    result = runner.run(SubagentRequest("分析这份代码"))

    assert result.ok is True
    assert result.result == "分析结论"
    assert result.rounds == 0


def test_counts_tool_rounds_and_returns_final_text():
    provider = FakeProvider([
        ProviderResponse(content="", tool_calls=[ToolCall("c1", "read_file", {"path": "a.py"})]),
        ProviderResponse(content="读完的结论", tool_calls=[]),
    ])
    runner = _runner(provider)

    result = runner.run(SubagentRequest("读文件并总结"))

    assert result.ok is True
    assert result.result == "读完的结论"
    assert result.rounds == 1


def test_truncates_goal():
    provider = FakeProvider([ProviderResponse(content="ok", tool_calls=[])])
    runner = _runner(provider, max_goal_chars=5)

    runner.run(SubagentRequest("1234567890"))

    user_contents = [m.content for m in provider.seen_messages[0] if m.role == "user"]
    assert user_contents == ["12345"]


def test_includes_context_fragment():
    provider = FakeProvider([ProviderResponse(content="ok", tool_calls=[])])
    runner = _runner(provider)

    runner.run(SubagentRequest("目标", context="背景资料"))

    system_contents = [m.content for m in provider.seen_messages[0] if m.role == "system"]
    assert any("背景资料" in c for c in system_contents)


def test_ok_false_when_loop_aborts():
    provider = FakeProvider([
        ProviderResponse(content="", tool_calls=[ToolCall("c1", "read_file", {"path": "a.py"})]),
    ])
    runner = _runner(provider, default_max_rounds=0)

    result = runner.run(SubagentRequest("读文件"))

    assert result.ok is False
    assert result.result == ""


def test_applies_default_allowed_tools_when_not_specified():
    provider = FakeProvider([ProviderResponse(content="ok", tool_calls=[])])
    registry = _registry()
    runner = SubagentRunner(provider, registry.subset, "你是子代理", default_allowed_tools=["read_file"])

    runner.run(SubagentRequest("目标"))

    tool_names = {schema["function"]["name"] for schema in provider.seen_tools[0]}
    assert tool_names == {"read_file"}


def test_uses_request_allowed_tools_over_default():
    provider = FakeProvider([ProviderResponse(content="ok", tool_calls=[])])
    registry = _registry()
    runner = SubagentRunner(provider, registry.subset, "你是子代理", default_allowed_tools=["read_file"])

    runner.run(SubagentRequest("目标", allowed_tools=["remember"]))

    tool_names = {schema["function"]["name"] for schema in provider.seen_tools[0]}
    assert tool_names == {"remember"}


def test_truncates_result():
    provider = FakeProvider([ProviderResponse(content="x" * 100, tool_calls=[])])
    runner = _runner(provider, max_result_chars=10)

    result = runner.run(SubagentRequest("目标"))

    assert result.result == "x" * 10


def test_researcher_role_adds_role_prompt_and_default_tools():
    provider = FakeProvider([ProviderResponse(content="ok", tool_calls=[])])
    runner = _runner(provider)

    runner.run(SubagentRequest("检索资料", role="researcher"))

    system_contents = [m.content for m in provider.seen_messages[0] if m.role == "system"]
    assert any("资料检索" in content and "来源" in content for content in system_contents)
    tool_names = {schema["function"]["name"] for schema in provider.seen_tools[0]}
    assert tool_names == {"read_file", "web_search", "fetch_page"}


def test_request_options_override_role_defaults():
    provider = FakeProvider([ProviderResponse(content="ok", tool_calls=[])])
    runner = _runner(provider)

    runner.run(SubagentRequest("检索资料", role="researcher", allowed_tools=["remember"], max_rounds=2))

    tool_names = {schema["function"]["name"] for schema in provider.seen_tools[0]}
    assert tool_names == {"remember"}


def test_unknown_role_is_rejected():
    provider = FakeProvider([ProviderResponse(content="ok", tool_calls=[])])
    runner = _runner(provider)

    try:
        runner.run(SubagentRequest("任务", role="unknown"))
    except ValueError as exc:
        assert "unknown" in str(exc)
    else:
        raise AssertionError("unknown role should be rejected")
