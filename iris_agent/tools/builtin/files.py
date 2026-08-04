from pathlib import Path

from iris_agent.tools.base import Tool, ToolInvocationError


def _safe_path(root: Path, relative: str) -> Path:
    root = root.resolve()
    target = (root / relative).resolve()
    if not target.is_relative_to(root):
        raise ToolInvocationError("path_outside_workspace", "路径超出工作区")
    return target


def build_read_file_tool(workspace_root: Path, max_chars: int = 20_000) -> Tool:
    def read_file(path: str):
        target = _safe_path(workspace_root, path)
        if not target.is_file():
            raise ToolInvocationError("file_not_found", f"文件不存在: {path}")
        try:
            content = target.read_text(encoding="utf-8")
        except UnicodeDecodeError as exc:
            raise ToolInvocationError("unsupported_encoding", "仅支持 UTF-8 文本文件") from exc
        return {"path": path, "content": content[:max_chars], "truncated": len(content) > max_chars}

    return Tool("read_file", "读取工作区内的 UTF-8 文本文件", {"type": "object", "properties": {"path": {"type": "string"}}, "required": ["path"]}, read_file)


def build_list_directory_tool(workspace_root: Path) -> Tool:
    def list_directory(path: str = "."):
        target = _safe_path(workspace_root, path)
        if not target.is_dir():
            raise ToolInvocationError("directory_not_found", f"目录不存在: {path}")
        entries = [{"name": item.name, "type": "directory" if item.is_dir() else "file"} for item in sorted(target.iterdir(), key=lambda item: item.name)]
        return {"path": path, "entries": entries}

    return Tool("list_directory", "列出工作区内目录的直接子项", {"type": "object", "properties": {"path": {"type": "string"}}}, list_directory)
