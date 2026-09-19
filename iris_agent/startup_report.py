"""Startup banner: record what this process actually loaded, and whether disk moved on.

This exists because of a failure mode that bit three times in one day: the running process
keeps using the code and configuration it read at boot, and nothing surfaced that. The
symptom was always "它还是回旧的那句话", and the cause was always "忘了重启".

The banner logs the effective values so a stale process is visible rather than inferred, and
compares the mtimes of ``agent.yaml`` and the package sources against the process start time
so "需要重启" is stated outright.
"""

from __future__ import annotations

import hashlib
import logging
from pathlib import Path
import time
from typing import Any

logger = logging.getLogger(__name__)

_WIDTH = 68


def _digest(path: Path) -> str | None:
    try:
        return hashlib.sha256(path.read_bytes()).hexdigest()[:8]
    except OSError:
        return None


def _fmt(stamp: float) -> str:
    return time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(stamp))


def _mtime(path: Path) -> float | None:
    try:
        return path.stat().st_mtime
    except OSError:
        return None


def _newest_source(package_root: Path) -> tuple[Path, float] | None:
    newest: tuple[Path, float] | None = None
    try:
        candidates = package_root.rglob("*.py")
        for path in candidates:
            if "__pycache__" in path.parts:
                continue
            stamp = _mtime(path)
            if stamp is not None and (newest is None or stamp > newest[1]):
                newest = (path, stamp)
    except OSError:
        return None
    return newest


def _search_sources(web_search: Any) -> str:
    """与 bootstrap 的装配逻辑保持一致，避免横幅报的和实际跑的不一样。"""
    names = []
    if getattr(web_search, "enable_tavily", False) and getattr(web_search, "tavily_api_key", ""):
        names.append("Tavily")
    names.append("Bing")
    if getattr(web_search, "enable_duckduckgo", False):
        names.append("DuckDuckGo")
    return "+".join(names)


def build_startup_banner(
    settings: Any,
    *,
    config_path: str | Path = "agent.yaml",
    package_root: str | Path | None = None,
    log_path: Path | None = None,
    started_at: float | None = None,
    pid: int | None = None,
) -> list[str]:
    """Return the banner as text lines. Never raises — a report must not block startup."""
    started = started_at if started_at is not None else time.time()
    root = Path(package_root) if package_root is not None else Path(__file__).resolve().parent
    config_file = Path(config_path)
    stale: list[str] = []

    lines = ["=" * _WIDTH, "Iris Agent 启动".center(_WIDTH), "=" * _WIDTH]
    lines.append(f"进程      pid={pid if pid is not None else '?'}  启动于 {_fmt(started)}")

    config_stamp = _mtime(config_file)
    if config_stamp is None:
        lines.append(f"配置      {config_file}  （读取不到）")
    else:
        digest = _digest(config_file)
        lines.append(f"配置      {config_file}  sha={digest or '?'}  mtime={_fmt(config_stamp)}")
        if config_stamp > started:
            stale.append("agent.yaml")

    newest = _newest_source(root)
    if newest is not None:
        rel = newest[0].relative_to(root) if newest[0].is_relative_to(root) else newest[0]
        lines.append(f"代码      最新改动 {_fmt(newest[1])}  ({rel})")
        if newest[1] > started:
            stale.append("源码")

    if log_path is not None:
        lines.append(f"日志      {log_path}")

    lines.append(f"模型      {getattr(settings.llm, 'model', '?')}")
    gateway = settings.gateway
    lines.append(
        "网关      "
        f"enabled={gateway.enabled}  qq={gateway.qq.enabled}  "
        f"napcat_auto_start={gateway.napcat_auto_start}  "
        f"allowed_users={','.join(gateway.qq.allowed_users) or '（空）'}"
    )
    lines.append(f"TTS       enabled={settings.tts.enabled}")

    web = settings.web_search
    tavily = "已配置" if getattr(web, "tavily_api_key", "") else "未配置"
    lines.append(
        f"联网      enabled={web.enabled}  源={_search_sources(web)}  tavily_key={tavily}"
    )

    tools = settings.tools
    lines.append(
        f"工作区    workspace_root={tools.workspace_root}  已启用工具={len(tools.enabled)}"
    )
    lines.append(f"提示词    system_prompt={len(settings.agent.system_prompt)} 字符")

    if stale:
        lines.append("-" * _WIDTH)
        lines.append(f"⚠ 磁盘上有比本进程更新的内容：{'、'.join(stale)}")
        lines.append("  这些改动不在当前进程里，需要重启才能生效。")

    lines.append("=" * _WIDTH)
    return lines


def report_startup(
    settings: Any,
    *,
    config_path: str | Path = "agent.yaml",
    package_root: str | Path | None = None,
    log_path: Path | None = None,
) -> list[str]:
    """Log the banner at INFO and return the same lines for the console."""
    try:
        lines = build_startup_banner(
            settings,
            config_path=config_path,
            package_root=package_root,
            log_path=log_path,
            started_at=time.time(),
            pid=_pid(),
        )
    except Exception:  # noqa: BLE001 - 诊断信息绝不能影响启动
        logger.exception("无法生成启动横幅")
        return []
    logger.info("启动横幅\n%s", "\n".join(lines))
    return lines


def _pid() -> int | None:
    try:
        import os

        return os.getpid()
    except Exception:  # noqa: BLE001
        return None
