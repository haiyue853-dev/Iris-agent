import logging
from logging.handlers import RotatingFileHandler

import pytest

import iris_agent.logging_setup as logging_setup
from iris_agent.logging_setup import configure_logging


@pytest.fixture()
def log_root():
    """把根 logger 恢复原状，避免测试之间互相污染级别和 handler。"""
    root = logging.getLogger()
    original_level = root.level
    yield root
    for handler in list(root.handlers):
        if isinstance(handler, RotatingFileHandler):
            root.removeHandler(handler)
            handler.close()
    if hasattr(root, "_iris_log_path"):
        delattr(root, "_iris_log_path")
    root.setLevel(original_level)
    logging_setup._configured = False


def _flush(root: logging.Logger) -> None:
    for handler in root.handlers:
        handler.flush()


def test_warnings_are_written_to_the_log_file(tmp_path, log_root):
    path = configure_logging(tmp_path, force=True)

    assert path == tmp_path / "iris.log"
    logging.getLogger("iris_agent.gateway.napcat").warning("NapCat 自动启动失败：路径不存在")
    _flush(log_root)

    content = path.read_text(encoding="utf-8")
    assert "NapCat 自动启动失败：路径不存在" in content
    assert "WARNING" in content
    assert "iris_agent.gateway.napcat" in content


def test_repeated_calls_reuse_the_same_handler(tmp_path, log_root):
    first = configure_logging(tmp_path, force=True)
    second = configure_logging(tmp_path, force=True)

    assert first == second
    assert sum(isinstance(h, RotatingFileHandler) for h in log_root.handlers) == 1


def test_calling_again_without_force_keeps_the_first_destination(tmp_path, log_root):
    """幂等：应用里可能被多处调用，不该因此切换文件或叠加 handler。"""
    first = configure_logging(tmp_path / "a", force=True)
    second = configure_logging(tmp_path / "b")

    assert second == first
    assert not (tmp_path / "b").exists()


def test_a_broken_log_directory_does_not_raise(tmp_path, log_root):
    """日志目录建不起来时必须安静降级——绝不能因此启动不了应用。"""
    blocker = tmp_path / "logs"
    blocker.write_text("这是一个文件，不是目录", encoding="utf-8")

    assert configure_logging(blocker, force=True) is None
    assert not blocker.is_dir()


def test_level_can_come_from_the_environment(tmp_path, log_root, monkeypatch):
    monkeypatch.setenv("IRIS_LOG_LEVEL", "ERROR")

    configure_logging(tmp_path, force=True)

    assert log_root.level == logging.ERROR


def test_an_unparsable_level_falls_back_to_info(tmp_path, log_root, monkeypatch):
    monkeypatch.setenv("IRIS_LOG_LEVEL", "not-a-level")

    configure_logging(tmp_path, force=True)

    assert log_root.level == logging.INFO


def test_chatty_libraries_are_quieted(tmp_path, log_root):
    configure_logging(tmp_path, force=True)

    assert logging.getLogger("uvicorn.access").level == logging.WARNING
    assert logging.getLogger("httpx").level == logging.WARNING
