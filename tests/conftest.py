"""Shared pytest configuration.

Why this file exists: on this machine the default pytest basetemp
(``%TEMP%/pytest-of-<user>``) can end up with a security descriptor that the logged-in user
is absent from — readable, but undeletable and unrenamable. It happens when the test run is
spawned from a sandboxed/restricted context (agent sessions), not from a normal terminal.

The symptom is nasty because it is not a clear error: pytest can still *create* its numbered
directories inside, so tests appear to run, but it cannot *clean up* the previous run's ones.
That shows up either as a bare "empty output, exit 1", or as a run that takes 9x longer while
deletion retries. `--basetemp` with a fresh directory sidesteps it entirely, but forcing that
on everyone would scatter undeletable scratch directories across %TEMP% for normal users too.

So: probe the default, and only fall back when it is actually sealed.
"""

from __future__ import annotations

import getpass
import os
from pathlib import Path
import tempfile
import time


def _is_sealed(directory: Path) -> bool:
    """True when we can write inside `directory` but cannot remove what we wrote."""
    probe = directory / f".iris-write-probe-{os.getpid()}"
    try:
        probe.mkdir(parents=True, exist_ok=True)
        probe.rmdir()
    except OSError:
        return True
    return False


def pytest_configure(config) -> None:
    if config.option.basetemp is not None:
        return  # 用户显式指定了，尊重它

    default = Path(tempfile.gettempdir()) / f"pytest-of-{getpass.getuser()}"
    try:
        default.mkdir(parents=True, exist_ok=True)
    except OSError:
        pass

    if not _is_sealed(default):
        return  # 正常环境，用 pytest 默认行为

    config.option.basetemp = str(
        Path(tempfile.gettempdir()) / f"iris-pytest-{os.getpid()}-{int(time.time())}"
    )
