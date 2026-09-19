"""Gateway-side tool policy.

Chat platforms have no approval UI, so :class:`GatewayService` cannot ask a human before a
sensitive tool call. It applies this fixed policy instead.

The dividing line is not "read vs write vs execute" but **whether the change would redefine
the agent's own behaviour or configuration**. Writing ordinary project data is fine; rewriting
``agent.yaml``, the agent package, the skill definitions or the model profiles is not. This
mirrors the rule ``tools/builtin/memory_tool.py`` already applies to long-term memory, where
prompts, roles and workflow rules are refused.

The policy governs gateway traffic only — the web UI keeps its approval dialog.
"""

from __future__ import annotations

from pathlib import Path

# 工作区根下的单个文件：命中即敏感（均以小写书写，比对时两侧都 casefold）
_SENSITIVE_FILES = frozenset({
    "agent.yaml",
    ".env",
    "server.py",
    "iris_agent.py",
    "requirements.txt",
    "pytest.ini",
    "start.ps1",
    "start.cmd",
    "loadnapcat.js",
})

# 多段相对路径：精确命中即敏感
_SENSITIVE_DATA_FILES = frozenset({
    ("data", "settings_profiles.json"),
    ("data", "settings_profiles.example.json"),
})

# 目录前缀：命中任一即敏感
_SENSITIVE_PREFIXES = (
    ("iris_agent",),
    (".git",),
    ("data", "skills"),
    ("data", "gateway"),
)

# 能绕过任何路径规则的执行类工具，网关上一律不批
_EXECUTION_TOOLS = frozenset({"run_command"})

# 需要审批、且允许按目标路径放行的写入类工具
_WRITE_TOOLS = frozenset({"write_file", "replace_in_file"})


def _relative_parts(root: Path, raw: object) -> tuple[str, ...] | None:
    """把工具传入的 path 规约成小写的相对路径片段；越界或非法时返回 None。"""
    if not isinstance(raw, str) or not raw.strip():
        return None
    try:
        target = (root / raw).resolve()
        relative = target.relative_to(Path(root).resolve())
    except (OSError, RuntimeError, ValueError):
        return None
    return tuple(part.casefold() for part in relative.parts)


def is_sensitive_path(root: Path, raw: object) -> bool:
    """目标路径是否落在定义 agent 行为与配置的位置上。

    路径无法规约（越界、空值、非法字符）时一律视为敏感，宁可拒绝。
    """
    parts = _relative_parts(root, raw)
    if parts is None or not parts:
        return True
    if len(parts) == 1 and parts[0] in _SENSITIVE_FILES:
        return True
    if parts in _SENSITIVE_DATA_FILES:
        return True
    return any(parts[: len(prefix)] == prefix for prefix in _SENSITIVE_PREFIXES)


def decide_tool_approval(
    name: object,
    arguments: object,
    workspace_root: Path | None,
) -> bool:
    """网关侧是否批准一次待审批的工具调用。返回 True 放行，False 拒绝。"""
    tool_name = str(name or "")
    if tool_name in _EXECUTION_TOOLS:
        return False
    if tool_name not in _WRITE_TOOLS:
        # 其余需要审批的工具维持原行为：聊天平台无法确认，一律拒绝。
        return False
    if workspace_root is None:
        return False
    path = arguments.get("path") if isinstance(arguments, dict) else None
    return not is_sensitive_path(workspace_root, path)
