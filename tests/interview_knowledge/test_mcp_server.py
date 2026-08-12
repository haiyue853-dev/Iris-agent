import io
import json

from iris_agent.interview_knowledge import mcp_server


def test_mcp_server_lists_interview_tools(tmp_path, monkeypatch):
    monkeypatch.setattr("sys.stdin", io.StringIO('{"jsonrpc":"2.0","id":1,"method":"initialize","params":{}}\n{"jsonrpc":"2.0","id":2,"method":"tools/list","params":{}}\n'))
    output = io.StringIO()
    monkeypatch.setattr("sys.stdout", output)

    mcp_server.serve(tmp_path / "knowledge.json")

    responses = [json.loads(line) for line in output.getvalue().splitlines()]
    assert responses[0]["result"]["serverInfo"]["name"] == "iris-interview-web"
    assert [item["name"] for item in responses[1]["result"]["tools"]] == ["search_interview_sources", "extract_interview_qa", "save_interview_qa"]
