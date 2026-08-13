from pathlib import Path

from iris_agent.core.agent import AgentLoop
from iris_agent.core.models import Message, ProviderResponse, ToolCall
from iris_agent.mcp_center.service import McpCenterService
from iris_agent.mcp_center.tools import register_mcp_tools
from iris_agent.tools.registry import ToolRegistry


class _Provider:
    def __init__(self, *responses: ProviderResponse) -> None:
        self.responses = list(responses)
        self.messages: list[list[Message]] = []

    def complete(self, messages: list[Message], tools):
        self.messages.append(messages)
        return self.responses.pop(0)


def test_agent_executes_an_allowlisted_read_only_mcp_tool_and_returns_its_result(tmp_path: Path, monkeypatch) -> None:
    mcp = McpCenterService(tmp_path / "mcp.json")
    server = mcp.create(name="Browser", command="node", args=("server.js",), allowed_tools=("get_page_source",))
    mcp.set_enabled(server.id, True)
    monkeypatch.setattr(mcp, "discover_tools", lambda server_id: ({
        "name": "get_page_source", "description": "Read the open page", "annotations": {"readOnlyHint": True},
        "inputSchema": {"type": "object", "properties": {}},
    },))
    monkeypatch.setattr(mcp, "call_tool", lambda server_id, name, arguments: {"content": [{"type": "text", "text": "<title>Example Domain</title>"}]})
    registry = ToolRegistry()
    register_mcp_tools(registry, mcp)
    tool_name = f"mcp__{server.id}__get_page_source"
    provider = _Provider(
        ProviderResponse(tool_calls=[ToolCall("mcp-call", tool_name, {})]),
        ProviderResponse(content="页面标题是 Example Domain。"),
    )

    events = list(AgentLoop(provider, registry).run([Message(role="user", content="读取当前页面")]))

    assert [event.type for event in events] == ["react_step", "tool_started", "tool_finished", "react_step", "react_step", "text_delta", "message_completed"]
    assert events[2].data["result"] == {"content": [{"type": "text", "text": "<title>Example Domain</title>"}]}
    assert provider.messages[1][-1].role == "tool"
    assert "Example Domain" in provider.messages[1][-1].content
