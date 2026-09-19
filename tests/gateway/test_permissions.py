from pathlib import Path

import pytest

from iris_agent.gateway.permissions import decide_tool_approval, is_sensitive_path


@pytest.fixture()
def root(tmp_path: Path) -> Path:
    return tmp_path


@pytest.mark.parametrize(
    "path",
    [
        "agent.yaml",
        ".env",
        "server.py",
        "iris_agent.py",
        "requirements.txt",
        "pytest.ini",
        "start.ps1",
        "start.cmd",
        "loadNapCat.js",
        "iris_agent/core/agent.py",
        "iris_agent/gateway/permissions.py",
        "data/skills/my-skill/SKILL.md",
        "data/settings_profiles.json",
        "data/gateway/sessions.json",
        ".git/config",
    ],
)
def test_sensitive_paths_are_recognised(root: Path, path: str) -> None:
    assert is_sensitive_path(root, path) is True


@pytest.mark.parametrize(
    "path",
    [
        "notes/todo.md",
        "data/reports/weekly.md",
        "data/chat_attachments/receipt.png",
        "data/knowledge/files/doc.md",
        "data/memory/memory.json",
        "data/tasks/today.md",
        "docs/idea.md",
        "README.md",
    ],
)
def test_ordinary_paths_are_allowed(root: Path, path: str) -> None:
    assert is_sensitive_path(root, path) is False


def test_sensitive_match_ignores_case_and_separators(root: Path) -> None:
    assert is_sensitive_path(root, "AGENT.YAML") is True
    assert is_sensitive_path(root, "Iris_Agent/core/agent.py") is True
    assert is_sensitive_path(root, r"data\skills\x.md") is True


def test_parent_segments_cannot_escape_the_check(root: Path) -> None:
    assert is_sensitive_path(root, "iris_agent/../agent.yaml") is True
    assert is_sensitive_path(root, "notes/../agent.yaml") is True
    assert is_sensitive_path(root, "../outside.txt") is True


def test_absolute_paths_outside_the_workspace_are_sensitive(root: Path) -> None:
    assert is_sensitive_path(root, str(root.parent / "elsewhere.txt")) is True


def test_absolute_sensitive_path_is_sensitive(root: Path) -> None:
    assert is_sensitive_path(root, str(root / "agent.yaml")) is True


@pytest.mark.parametrize("raw", [None, "", "   ", 123, ["agent.yaml"]])
def test_unusable_paths_are_treated_as_sensitive(root: Path, raw: object) -> None:
    assert is_sensitive_path(root, raw) is True


def test_write_to_ordinary_path_is_approved(root: Path) -> None:
    assert decide_tool_approval("write_file", {"path": "notes/todo.md"}, root) is True
    assert decide_tool_approval("replace_in_file", {"path": "docs/idea.md"}, root) is True


@pytest.mark.parametrize(
    "name",
    ["write_file", "replace_in_file"],
)
def test_write_to_sensitive_path_is_refused(root: Path, name: str) -> None:
    assert decide_tool_approval(name, {"path": "agent.yaml"}, root) is False
    assert decide_tool_approval(name, {"path": "iris_agent/core/agent.py"}, root) is False


def test_run_command_is_always_refused(root: Path) -> None:
    assert decide_tool_approval("run_command", {"command": "git status"}, root) is False
    assert decide_tool_approval("run_command", {}, root) is False


def test_other_approval_tools_keep_being_refused(root: Path) -> None:
    assert decide_tool_approval("some_tool", {}, root) is False
    assert decide_tool_approval("delegate_task", {"goal": "x"}, root) is False


def test_write_without_a_path_is_refused(root: Path) -> None:
    assert decide_tool_approval("write_file", {}, root) is False
    assert decide_tool_approval("write_file", None, root) is False
    assert decide_tool_approval("write_file", {"path": None}, root) is False


def test_missing_workspace_root_refuses_writes() -> None:
    assert decide_tool_approval("write_file", {"path": "notes/todo.md"}, None) is False
