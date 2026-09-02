from iris_agent.tools.builtin.files import build_list_directory_tool, build_read_file_tool, build_replace_in_file_tool, build_run_command_tool, build_write_file_tool


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


def test_write_and_replace_require_workspace_paths(tmp_path):
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    write = build_write_file_tool(workspace)
    created = write.invoke({"path": "nested/a.txt", "content": "before"})
    assert created.ok and created.value["overwritten"] is False
    assert "+before" in created.value["diff"]
    assert not write.invoke({"path": "nested/a.txt", "content": "again"}).ok
    replaced = build_replace_in_file_tool(workspace).invoke({"path": "nested/a.txt", "old_text": "before", "new_text": "after"})
    assert replaced.ok
    assert "-before" in replaced.value["diff"] and "+after" in replaced.value["diff"]
    assert (workspace / "nested" / "a.txt").read_text(encoding="utf-8") == "after"
    assert not write.invoke({"path": "../outside.txt", "content": "no"}).ok


def test_run_command_rejects_shell_chains_and_unapproved_programs(tmp_path):
    tool = build_run_command_tool(tmp_path)
    assert tool.invoke({"command": "python -V"}).ok
    assert tool.invoke({"command": "python -V; git status"}).error_code == "unsafe_command"
    assert tool.invoke({"command": "cmd /c dir"}).error_code == "command_not_allowed"
