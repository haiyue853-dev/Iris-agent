import subprocess
from unittest.mock import Mock, patch

import pytest

from iris_agent.gateway.napcat import NapCatError, NapCatLauncher


def test_launches_configured_napcat_once(tmp_path):
    executable = tmp_path / "NapCat.Shell.exe"
    executable.write_text("stub", encoding="utf-8")
    launcher = NapCatLauncher(tmp_path / "napcat.json")
    launcher.save_path(str(executable))
    process = Mock()
    process.poll.return_value = None

    with patch("iris_agent.gateway.napcat.subprocess.Popen", return_value=process) as popen:
        first = launcher.launch()
        second = launcher.launch()

    assert first["already_running"] is False
    assert second["already_running"] is True
    popen.assert_called_once_with([str(executable)], cwd=str(tmp_path), shell=False)


def test_launches_batch_without_console_window(tmp_path):
    launcher_file = tmp_path / "launcher.bat"
    launcher_file.write_text("@echo off", encoding="utf-8")
    launcher = NapCatLauncher(tmp_path / "napcat.json")
    launcher.save_path(str(launcher_file))
    process = Mock()
    process.poll.return_value = None

    with patch("iris_agent.gateway.napcat.subprocess.Popen", return_value=process) as popen:
        launcher.launch()

    popen.assert_called_once_with(
        ["cmd.exe", "/d", "/c", str(launcher_file)],
        cwd=str(tmp_path),
        shell=False,
        creationflags=subprocess.CREATE_NO_WINDOW,
    )


def test_prefers_user_launcher_when_standard_launcher_requires_elevation(tmp_path):
    standard_launcher = tmp_path / "launcher.bat"
    standard_launcher.write_text("@echo off", encoding="utf-8")
    user_launcher = tmp_path / "launcher-user.bat"
    user_launcher.write_text("@echo off", encoding="utf-8")
    launcher = NapCatLauncher(tmp_path / "napcat.json")
    launcher.save_path(str(standard_launcher))
    process = Mock()
    process.poll.return_value = None

    with patch("iris_agent.gateway.napcat.subprocess.Popen", return_value=process) as popen:
        launcher.launch()

    popen.assert_called_once_with(
        ["cmd.exe", "/d", "/c", str(user_launcher)],
        cwd=str(tmp_path),
        shell=False,
        creationflags=subprocess.CREATE_NO_WINDOW,
    )
    assert launcher.path == str(user_launcher)


def test_matches_launcher_script_in_directory(tmp_path):
    launcher_file = tmp_path / "launcher.bat"
    launcher_file.write_text("@echo off", encoding="utf-8")
    launcher = NapCatLauncher(tmp_path / "napcat.json")

    result = launcher.match_directory(str(tmp_path))

    assert result["path"] == str(launcher_file)


def test_launch_requires_a_configured_path(tmp_path):
    launcher = NapCatLauncher(tmp_path / "napcat.json")

    with pytest.raises(NapCatError) as error:
        launcher.launch()

    assert error.value.code == "napcat_not_configured"
