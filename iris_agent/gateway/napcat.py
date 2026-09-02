"""Local NapCat process configuration and launcher."""

from __future__ import annotations

import json
from pathlib import Path
import subprocess
import threading


class NapCatError(Exception):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
        self.message = message


class NapCatLauncher:
    USER_LAUNCHERS = {
        "launcher.bat": "launcher-user.bat",
        "launcher-win10.bat": "launcher-win10-user.bat",
    }
    MATCH_CANDIDATES = (
        "launcher.bat",
        "launcher-win10.bat",
        "launcher-user.bat",
        "launcher-win10-user.bat",
    )
    def __init__(self, state_file: str | Path):
        self.state_file = Path(state_file)
        self._lock = threading.RLock()
        self._process: subprocess.Popen | None = None
        self._path = self._load_path()

    def _load_path(self) -> str:
        try:
            value = json.loads(self.state_file.read_text(encoding="utf-8")).get("path", "")
        except (OSError, ValueError, AttributeError):
            return ""
        return value.strip() if isinstance(value, str) else ""

    @property
    def path(self) -> str:
        return self._path

    def _running(self) -> bool:
        return self._process is not None and self._process.poll() is None

    def status(self) -> dict[str, object]:
        with self._lock:
            return {"path": self._path, "configured": bool(self._path), "running": self._running()}

    def save_path(self, value: str) -> dict[str, object]:
        path = value.strip()
        if path and not Path(path).is_absolute():
            raise NapCatError("napcat_path_must_be_absolute", "NapCat 路径必须是绝对路径")
        if path and (not Path(path).exists() or not Path(path).is_file()):
            raise NapCatError("napcat_path_not_found", "NapCat 可执行文件不存在")
        with self._lock:
            self.state_file.parent.mkdir(parents=True, exist_ok=True)
            self.state_file.write_text(json.dumps({"path": path}, ensure_ascii=False, indent=2), encoding="utf-8")
            self._path = path
            return self.status()

    def match_directory(self, value: str) -> dict[str, object]:
        directory = value.strip()
        if not directory or not Path(directory).is_absolute():
            raise NapCatError("napcat_directory_must_be_absolute", "NapCat 文件夹路径必须是绝对路径")
        folder = Path(directory)
        if not folder.exists() or not folder.is_dir():
            raise NapCatError("napcat_directory_not_found", "NapCat 文件夹不存在")
        for candidate in self.MATCH_CANDIDATES:
            path = folder / candidate
            if path.is_file():
                return self.save_path(str(path))
        raise NapCatError("napcat_launcher_not_found", "文件夹中未找到 NapCat 启动脚本")

    def launch(self) -> dict[str, object]:
        with self._lock:
            if not self._path:
                raise NapCatError("napcat_not_configured", "请先配置 NapCat 可执行文件路径")
            executable = Path(self._path)
            if not executable.exists() or not executable.is_file():
                raise NapCatError("napcat_path_not_found", "NapCat 可执行文件不存在，请重新配置路径")
            user_launcher = self.USER_LAUNCHERS.get(executable.name.lower())
            if user_launcher:
                user_executable = executable.with_name(user_launcher)
                if user_executable.is_file():
                    executable = user_executable
                    self.save_path(str(executable))
            if self._running():
                return {"path": self._path, "configured": True, "running": True, "already_running": True}
            try:
                command = [str(executable)]
                process_options: dict[str, object] = {"cwd": str(executable.parent), "shell": False}
                if executable.suffix.lower() in {".bat", ".cmd"}:
                    command = ["cmd.exe", "/d", "/c", str(executable)]
                    process_options["creationflags"] = subprocess.CREATE_NO_WINDOW
                self._process = subprocess.Popen(command, **process_options)
            except OSError as exc:
                raise NapCatError("napcat_launch_failed", f"NapCat 启动失败：{exc}") from exc
            return {"path": self._path, "configured": True, "running": True, "already_running": False}
