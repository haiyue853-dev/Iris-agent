from __future__ import annotations

from pathlib import Path
import subprocess
import threading
import time
from typing import Callable
from urllib.parse import urlparse

from iris_agent.config.settings import TtsSettings

from .client import GptSovitsClient
from .errors import TtsUnavailableError


class GptSovitsProcessManager:
    def __init__(
        self,
        settings: TtsSettings,
        client: GptSovitsClient,
        *,
        start_process: Callable = subprocess.Popen,
        sleep: Callable[[float], None] = time.sleep,
        monotonic: Callable[[], float] = time.monotonic,
    ) -> None:
        self.settings = settings
        self.client = client
        self._start_process = start_process
        self._sleep = sleep
        self._monotonic = monotonic
        self._lock = threading.Lock()
        self._process = None
        self._ready = False
        self._status = "idle"
        self._status_detail = ""
        self._status_lock = threading.Lock()
        self._warmup_thread: threading.Thread | None = None

    @property
    def status(self) -> str:
        with self._status_lock:
            return self._status

    @property
    def status_detail(self) -> str:
        with self._status_lock:
            return self._status_detail

    def start_warmup(self) -> threading.Thread:
        with self._status_lock:
            if self._warmup_thread is not None and self._warmup_thread.is_alive():
                return self._warmup_thread
            self._status = "starting"
            self._status_detail = ""
            thread = threading.Thread(target=self._run_warmup, daemon=True, name="iris-tts-warmup")
            self._warmup_thread = thread
            thread.start()
            return thread

    def _run_warmup(self) -> None:
        try:
            self.ensure_ready()
        except Exception as exc:
            self._set_status("failed", str(exc))
        else:
            self._set_status("ready")

    def _set_status(self, status: str, detail: str = "") -> None:
        with self._status_lock:
            self._status = status
            self._status_detail = detail

    def ensure_ready(self) -> None:
        if self._ready:
            if self.client.is_healthy():
                self._set_status("ready")
                return
            self._ready = False
        self._set_status("starting")
        try:
            with self._lock:
                if self._ready:
                    self._set_status("ready")
                    return
                if not self.client.is_healthy():
                    self._validate_files()
                    self._process = self._launch()
                    self._wait_until_healthy()
                self.client.set_weights()
                warmup = getattr(self.client, "warmup", None)
                if callable(warmup):
                    warmup()
                self._ready = True
        except Exception as exc:
            self._set_status("failed", str(exc))
            raise
        self._set_status("ready")

    def close(self) -> None:
        process = self._process
        if process is None or process.poll() is not None:
            return
        process.terminate()
        try:
            process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=5)

    def _launch(self):
        root = self.settings.root_directory
        python = root / "runtime" / "python.exe"
        parsed = urlparse(self.settings.base_url)
        host = parsed.hostname or "127.0.0.1"
        port = parsed.port or 9880
        command = [
            str(python),
            "-I",
            "api_v2.py",
            "-a",
            host,
            "-p",
            str(port),
            "-c",
            "GPT_SoVITS/configs/tts_infer.yaml",
        ]
        return self._start_process(
            command,
            cwd=str(root),
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )

    def _wait_until_healthy(self) -> None:
        deadline = self._monotonic() + self.settings.startup_timeout_seconds
        while self._monotonic() < deadline:
            if self.client.is_healthy():
                return
            if self._process is not None and self._process.poll() is not None:
                raise TtsUnavailableError("GPT-SoVITS 启动失败")
            self._sleep(0.5)
        raise TtsUnavailableError("等待 GPT-SoVITS 启动超时")

    def _validate_files(self) -> None:
        root = self.settings.root_directory
        required: tuple[tuple[Path, str], ...] = (
            (root / "runtime" / "python.exe", "GPT-SoVITS Python 运行时"),
            (root / "api_v2.py", "GPT-SoVITS API"),
            (root / "GPT_SoVITS" / "configs" / "tts_infer.yaml", "推理配置"),
            (self.settings.gpt_weights_path, "GPT 权重"),
            (self.settings.sovits_weights_path, "SoVITS 权重"),
            (self.settings.reference_audio_path, "参考音频"),
        )
        missing = [label for path, label in required if not path.is_file()]
        if missing:
            raise TtsUnavailableError(f"缺少语音文件：{'、'.join(missing)}")
