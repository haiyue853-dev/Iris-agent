import logging
import time
from pathlib import Path
from types import SimpleNamespace

import pytest

from iris_agent.startup_report import build_startup_banner, report_startup


def _settings(
    *,
    model: str = "deepseek-chat",
    napcat_auto_start: bool = True,
    qq_enabled: bool = True,
    tts_enabled: bool = True,
    web_enabled: bool = True,
    enable_tavily: bool = True,
    tavily_api_key: str = "",
    enable_duckduckgo: bool = False,
    system_prompt: str = "你是 Iris Agent。",
    tools: tuple[str, ...] = ("read_file",),
) -> SimpleNamespace:
    return SimpleNamespace(
        llm=SimpleNamespace(model=model),
        gateway=SimpleNamespace(
            enabled=True,
            napcat_auto_start=napcat_auto_start,
            qq=SimpleNamespace(enabled=qq_enabled, allowed_users=["1905499552"]),
        ),
        tts=SimpleNamespace(enabled=tts_enabled),
        web_search=SimpleNamespace(
            enabled=web_enabled,
            enable_tavily=enable_tavily,
            tavily_api_key=tavily_api_key,
            enable_duckduckgo=enable_duckduckgo,
        ),
        tools=SimpleNamespace(workspace_root=".", enabled=tools),
        agent=SimpleNamespace(system_prompt=system_prompt),
    )


def _banner(settings, tmp_path: Path, *, started_at: float, config_name: str = "agent.yaml"):
    config = tmp_path / config_name
    config.write_text("gateway: {}\n", encoding="utf-8")
    return build_startup_banner(
        settings,
        config_path=config,
        package_root=tmp_path / "package",
        started_at=started_at,
        pid=1234,
    )


def _text(lines: list[str]) -> str:
    return "\n".join(lines)


def test_banner_reports_the_effective_values(tmp_path):
    settings = _settings(napcat_auto_start=True)

    text = _text(_banner(settings, tmp_path, started_at=time.time() + 60))

    assert "Iris Agent 启动" in text
    assert "pid=1234" in text
    assert "deepseek-chat" in text
    assert "napcat_auto_start=True" in text
    assert "1905499552" in text
    assert "system_prompt=" in text
    assert "已启用工具=1" in text


def test_tavily_is_only_listed_when_a_key_is_present(tmp_path):
    """横幅必须和 bootstrap 的装配逻辑一致，否则又是一处「说的和跑的不一样」。"""
    without_key = _text(_banner(_settings(tavily_api_key=""), tmp_path, started_at=time.time() + 60))
    with_key = _text(_banner(_settings(tavily_api_key="tvly-xxx"), tmp_path, started_at=time.time() + 60))

    assert "源=Bing" in without_key
    assert "tavily_key=未配置" in without_key
    assert "源=Tavily+Bing" in with_key
    assert "tavily_key=已配置" in with_key


def test_duckduckgo_is_listed_when_enabled(tmp_path):
    text = _text(
        _banner(
            _settings(tavily_api_key="", enable_duckduckgo=True),
            tmp_path,
            started_at=time.time() + 60,
        )
    )

    assert "源=Bing+DuckDuckGo" in text


def test_a_config_edited_after_startup_is_flagged(tmp_path):
    """核心价值：改了配置但没重启，必须直接说出来。"""
    settings = _settings()
    config = tmp_path / "agent.yaml"
    config.write_text("gateway: {}\n", encoding="utf-8")
    long_ago = time.time() - 3600

    text = _text(
        build_startup_banner(
            settings,
            config_path=config,
            package_root=tmp_path / "package",
            started_at=long_ago,
        )
    )

    assert "磁盘上有比本进程更新的内容" in text
    assert "agent.yaml" in text
    assert "需要重启才能生效" in text


def test_a_source_file_edited_after_startup_is_flagged(tmp_path):
    settings = _settings()
    config = tmp_path / "agent.yaml"
    config.write_text("gateway: {}\n", encoding="utf-8")
    package = tmp_path / "package"
    package.mkdir()
    (package / "changed_module.py").write_text("x = 1\n", encoding="utf-8")

    text = _text(
        build_startup_banner(
            settings,
            config_path=config,
            package_root=package,
            started_at=time.time() - 3600,
        )
    )

    assert "⚠ 磁盘上有比本进程更新的内容" in text
    assert "源码" in text
    assert "changed_module.py" in text


def test_a_clean_start_prints_no_warning(tmp_path):
    settings = _settings()
    config = tmp_path / "agent.yaml"
    config.write_text("gateway: {}\n", encoding="utf-8")

    text = _text(
        build_startup_banner(
            settings,
            config_path=config,
            package_root=tmp_path / "package",
            started_at=time.time() + 60,
        )
    )

    assert "⚠" not in text
    assert "需要重启" not in text


def test_report_startup_logs_the_banner_and_returns_it(tmp_path, caplog):
    settings = _settings()

    with caplog.at_level(logging.INFO, logger="iris_agent.startup_report"):
        lines = report_startup(settings, config_path=tmp_path / "missing.yaml", package_root=tmp_path)

    assert lines and "Iris Agent 启动" in "\n".join(lines)
    assert "Iris Agent 启动" in caplog.text


def test_report_startup_never_raises_on_broken_settings(tmp_path, caplog):
    """诊断信息不能反过来把启动搞挂。"""
    with caplog.at_level(logging.INFO, logger="iris_agent.startup_report"):
        lines = report_startup(object(), config_path=tmp_path / "missing.yaml", package_root=tmp_path)

    assert lines == []


@pytest.mark.parametrize("key", ["", None])
def test_missing_tavily_key_is_reported_as_unconfigured(tmp_path, key):
    text = _text(_banner(_settings(tavily_api_key=key), tmp_path, started_at=time.time() + 60))

    assert "tavily_key=未配置" in text
