import io
import json

from iris_agent.interview_knowledge import mcp_server


def test_mcp_server_advertises_read_and_write_tools(tmp_path, monkeypatch):
    monkeypatch.setattr("sys.stdin", io.StringIO('{"jsonrpc":"2.0","id":1,"method":"initialize","params":{}}\n{"jsonrpc":"2.0","id":2,"method":"tools/list","params":{}}\n'))
    output = io.StringIO()
    monkeypatch.setattr("sys.stdout", output)

    mcp_server.serve(tmp_path / "knowledge.json")

    tools = json.loads(output.getvalue().splitlines()[1])["result"]["tools"]
    assert [tool["name"] for tool in tools] == ["search_interview_sources", "extract_interview_qa", "save_interview_qa"]
    assert tools[0]["annotations"]["readOnlyHint"] is True
    assert "annotations" not in tools[2]
