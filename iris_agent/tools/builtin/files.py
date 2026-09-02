from pathlib import Path
from difflib import unified_diff
import shlex
import subprocess
import threading
import time
from queue import Empty, Queue

from iris_agent.tools.base import Tool, ToolInvocationError


_command_lock = threading.RLock()
_active_commands: set[subprocess.Popen[str]] = set()
_cancelled_commands: set[int] = set()


def cancel_active_commands() -> int:
    """Terminate running workspace commands. The task queue executes one chat at a time."""
    with _command_lock:
        commands = tuple(_active_commands)
        for process in commands:
            _cancelled_commands.add(id(process))
            if process.poll() is None:
                try: process.terminate()
                except OSError: pass
    return len(commands)


class CommandExecution:
    """A cancellable command with line-oriented output for the Agent event stream."""
    def __init__(self, args: list[str], command: str, cwd: Path, timeout: int, max_output_chars: int, root: Path) -> None:
        self.args, self.command, self.cwd, self.timeout, self.max_output_chars, self.root = args, command, cwd, timeout, max_output_chars, root
        self.process: subprocess.Popen[str] | None = None
        self.result: dict | None = None

    def cancel(self) -> None:
        process = self.process
        if process is not None and process.poll() is None:
            with _command_lock: _cancelled_commands.add(id(process))
            try: process.terminate()
            except OSError: pass

    def stream(self):
        started = time.monotonic(); lines: Queue[str] = Queue(); timed_out = False
        process = subprocess.Popen(self.args, cwd=self.cwd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, encoding="utf-8", errors="replace", shell=False, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        self.process = process
        with _command_lock: _active_commands.add(process)
        def read_lines() -> None:
            if process.stdout is not None:
                for line in iter(process.stdout.readline, ""): lines.put(line)
        reader = threading.Thread(target=read_lines, name="iris-command-output", daemon=True); reader.start()
        output: list[str] = []
        try:
            while process.poll() is None or not lines.empty():
                if time.monotonic() - started >= self.timeout and process.poll() is None:
                    timed_out = True; self.cancel()
                try:
                    line = lines.get(timeout=.08)
                    output.append(line)
                    yield {"output": line}
                except Empty:
                    pass
            reader.join(timeout=.2)
            while not lines.empty():
                line = lines.get_nowait(); output.append(line); yield {"output": line}
        finally:
            if process.poll() is None: self.cancel()
            try: process.wait(timeout=3)
            except subprocess.TimeoutExpired: process.kill(); process.wait()
            with _command_lock:
                _active_commands.discard(process)
                cancelled = id(process) in _cancelled_commands
                _cancelled_commands.discard(id(process))
        text = "".join(output); clipped = text[:self.max_output_chars]; duration_ms = round((time.monotonic() - started) * 1000)
        self.result = {"command": self.command, "cwd": str(self.cwd.relative_to(self.root.resolve())), "exit_code": process.returncode, "exitCode": process.returncode, "timed_out": timed_out, "cancelled": cancelled, "duration_ms": duration_ms, "durationMs": duration_ms, "output": clipped, "stdout": clipped, "truncated": len(text) > self.max_output_chars}


def _safe_path(root: Path, relative: str) -> Path:
    root = root.resolve()
    target = (root / relative).resolve()
    if not target.is_relative_to(root):
        raise ToolInvocationError("path_outside_workspace", "路径超出工作区")
    return target


def _text_diff(before: str, after: str, path: str) -> str:
    lines = list(unified_diff(before.splitlines(), after.splitlines(), fromfile=f"a/{path}", tofile=f"b/{path}", lineterm=""))
    return "\n".join(lines[:240]) + ("\n… diff 已截断" if len(lines) > 240 else "")


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


def build_write_file_tool(workspace_root: Path, max_chars: int = 200_000) -> Tool:
    def write_file(path: str, content: str, overwrite: bool = False):
        if len(content) > max_chars:
            raise ToolInvocationError("content_too_large", f"文件内容不能超过 {max_chars} 个字符")
        target = _safe_path(workspace_root, path)
        existed = target.exists()
        if existed and not overwrite:
            raise ToolInvocationError("file_exists", "文件已存在；如确认覆盖请设置 overwrite=true")
        if target.is_dir():
            raise ToolInvocationError("path_is_directory", "目标路径是目录")
        if existed:
            try: previous = target.read_text(encoding="utf-8")
            except UnicodeDecodeError as exc: raise ToolInvocationError("unsupported_encoding", "仅支持覆盖 UTF-8 文本文件") from exc
        else:
            previous = ""
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")
        relative = str(target.relative_to(workspace_root.resolve()))
        return {"path": relative, "bytes_written": len(content.encode("utf-8")), "overwritten": existed, "diff": _text_diff(previous, content, relative)}

    return Tool("write_file", "在工作区创建或覆盖 UTF-8 文本文件；每次执行均需用户审批", {"type": "object", "properties": {"path": {"type": "string"}, "content": {"type": "string"}, "overwrite": {"type": "boolean"}}, "required": ["path", "content"], "additionalProperties": False}, write_file, requires_approval=True, approval_context={"risk": "workspace_write"})


def build_replace_in_file_tool(workspace_root: Path, max_chars: int = 200_000) -> Tool:
    def replace_in_file(path: str, old_text: str, new_text: str):
        if not old_text:
            raise ToolInvocationError("invalid_replacement", "old_text 不能为空")
        target = _safe_path(workspace_root, path)
        if not target.is_file():
            raise ToolInvocationError("file_not_found", f"文件不存在: {path}")
        try: content = target.read_text(encoding="utf-8")
        except UnicodeDecodeError as exc: raise ToolInvocationError("unsupported_encoding", "仅支持 UTF-8 文本文件") from exc
        count = content.count(old_text)
        if count != 1:
            raise ToolInvocationError("replacement_not_unique", f"old_text 必须在文件中恰好出现一次，当前出现 {count} 次")
        updated = content.replace(old_text, new_text, 1)
        if len(updated) > max_chars:
            raise ToolInvocationError("content_too_large", f"修改后的文件不能超过 {max_chars} 个字符")
        target.write_text(updated, encoding="utf-8")
        relative = str(target.relative_to(workspace_root.resolve()))
        return {"path": relative, "replaced": 1, "bytes_written": len(updated.encode("utf-8")), "diff": _text_diff(content, updated, relative)}

    return Tool("replace_in_file", "精确替换工作区 UTF-8 文件中的一处文本；每次执行均需用户审批", {"type": "object", "properties": {"path": {"type": "string"}, "old_text": {"type": "string"}, "new_text": {"type": "string"}}, "required": ["path", "old_text", "new_text"], "additionalProperties": False}, replace_in_file, requires_approval=True, approval_context={"risk": "workspace_write"})


def build_run_command_tool(workspace_root: Path, *, timeout_seconds: int = 60, max_output_chars: int = 20_000, allowed_commands: tuple[str, ...] = ("python", "pytest", "npm", "node", "git")) -> Tool:
    allowed = {item.casefold() for item in allowed_commands}
    forbidden = {"rm", "rmdir", "del", "erase", "remove-item", "rd"}

    def run_command(command: str, cwd: str = ".", timeout_seconds_override: int | None = None):
        if not command.strip() or any(token in command for token in ("|", "&", ";", ">", "<", "`", "$(`")):
            raise ToolInvocationError("unsafe_command", "命令不允许 shell 管道、重定向、串联或命令替换")
        try: args = shlex.split(command, posix=True)
        except ValueError as exc: raise ToolInvocationError("invalid_command", "命令格式无效") from exc
        if not args: raise ToolInvocationError("invalid_command", "命令不能为空")
        executable = Path(args[0]).name.casefold().removesuffix(".exe")
        if executable in forbidden or executable not in allowed:
            raise ToolInvocationError("command_not_allowed", f"仅允许执行: {', '.join(sorted(allowed))}")
        lower = [item.casefold() for item in args]
        if executable == "git" and any(item in {"reset", "clean"} for item in lower[1:]):
            raise ToolInvocationError("unsafe_command", "不允许 git reset 或 git clean")
        target = _safe_path(workspace_root, cwd)
        if not target.is_dir(): raise ToolInvocationError("directory_not_found", f"工作目录不存在: {cwd}")
        timeout = min(max(int(timeout_seconds_override or timeout_seconds), 1), timeout_seconds)
        return CommandExecution(args, command, target, timeout, max_output_chars, workspace_root)

    return Tool("run_command", "在受限工作区运行安全白名单命令；每次执行均需用户审批", {"type": "object", "properties": {"command": {"type": "string"}, "cwd": {"type": "string"}, "timeout_seconds_override": {"type": "integer"}}, "required": ["command"], "additionalProperties": False}, run_command, requires_approval=True, approval_context={"risk": "workspace_command", "allowed_commands": sorted(allowed)})
