"""Process-wide logging setup.

Before this module existed the project had no logging configuration at all: the ~13 modules
that call ``logging.getLogger`` fell back to the stdlib default, which only writes WARNING and
above to stderr. For an unattended QQ bot that means failures vanished the moment the console
window closed — an earlier investigation had to reverse-engineer whether NapCat auto-start had
run at all because nothing was recorded.

This attaches a rotating file handler so those records survive. It is deliberately additive:
no console handler is installed, so existing stdout/stderr behaviour is unchanged.
"""

from __future__ import annotations

import logging
from logging.handlers import RotatingFileHandler
import os
from pathlib import Path

DEFAULT_DIRECTORY = "logs"
DEFAULT_FILENAME = "iris.log"
DEFAULT_LEVEL = "INFO"
DEFAULT_MAX_BYTES = 5 * 1024 * 1024
DEFAULT_BACKUP_COUNT = 3

# 这些库在 INFO 下会淹没真正的应用日志（尤其 uvicorn 的逐请求 access log）。
_NOISY_LOGGERS = ("uvicorn.access", "httpx", "httpcore", "urllib3", "asyncio")

_configured = False


def _detach_file_handlers(root: logging.Logger) -> None:
    for handler in list(root.handlers):
        if isinstance(handler, RotatingFileHandler):
            root.removeHandler(handler)
            handler.close()


def configure_logging(
    directory: str | Path | None = None,
    *,
    filename: str | None = None,
    level: str | None = None,
    max_bytes: int = DEFAULT_MAX_BYTES,
    backup_count: int = DEFAULT_BACKUP_COUNT,
    force: bool = False,
) -> Path | None:
    """Attach a rotating file handler to the root logger. Idempotent unless ``force``.

    Pass ``force=True`` to re-point an already-configured process at a new directory.

    Returns the log path, or ``None`` when the handler could not be created — a broken log
    directory must never stop the application from starting.
    """
    global _configured
    root = logging.getLogger()
    if _configured and not force:
        return getattr(root, "_iris_log_path", None)
    if force:
        _detach_file_handlers(root)

    log_dir = Path(directory or os.environ.get("IRIS_LOG_DIR") or DEFAULT_DIRECTORY)
    log_name = filename or DEFAULT_FILENAME
    requested = (level or os.environ.get("IRIS_LOG_LEVEL") or DEFAULT_LEVEL).upper()
    resolved_level = getattr(logging, requested, logging.INFO)
    if not isinstance(resolved_level, int):
        resolved_level = logging.INFO

    try:
        log_dir.mkdir(parents=True, exist_ok=True)
        path = log_dir / log_name
        handler = RotatingFileHandler(
            path,
            maxBytes=max_bytes,
            backupCount=backup_count,
            encoding="utf-8",
        )
    except OSError:
        _configured = False
        return None

    handler.setFormatter(
        logging.Formatter("%(asctime)s %(levelname)-7s %(name)s: %(message)s")
    )
    root.addHandler(handler)
    root.setLevel(resolved_level)
    for name in _NOISY_LOGGERS:
        logging.getLogger(name).setLevel(logging.WARNING)

    # 记录路径供调用方与重复调用读取；挂在 logger 上以免引入模块级可变状态。
    root._iris_log_path = path  # type: ignore[attr-defined]
    _configured = True
    return path
