from iris_agent.tools.builtin.files import build_list_directory_tool, build_read_file_tool


def test_read_file_cannot_escape_workspace(tmp_path):
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    tool = build_read_file_tool(workspace, max_chars=1000)
    result = tool.invoke({"path": "../secret.txt"})
    assert result.ok is False
    assert result.error_code == "path_outside_workspace"


def test_read_file_limits_content(tmp_path):
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    (workspace / "long.txt").write_text("abcdef", encoding="utf-8")
    result = build_read_file_tool(workspace, max_chars=3).invoke({"path": "long.txt"})
    assert result.ok is True
    assert result.value["content"] == "abc"
    assert result.value["truncated"] is True


def test_list_directory_lists_direct_children(tmp_path):
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    (workspace / "a.txt").write_text("a", encoding="utf-8")
    result = build_list_directory_tool(workspace).invoke({"path": "."})
    assert result.value["entries"] == [{"name": "a.txt", "type": "file"}]
