from __future__ import annotations

import subprocess

import pytest

from alexa_mcp.config import AlexaSettings, ConfigError
from alexa_mcp import runner


def _settings(**overrides: object) -> AlexaSettings:
    defaults = dict(
        command="/tmp/alexa_remote_control.sh",
        base_args=tuple(),
        event_flag="-e",
        device_flag="-d",
        default_device="Kitchen Echo",
        allowed_routines=frozenset({"plug_on", "plug_off"}),
        allowed_music_actions=frozenset({"play", "stop"}),
        timeout_seconds=10,
        health_check_args=tuple(),
        music_play_routine=None,
        music_stop_routine=None,
        max_query_length=120,
    )
    defaults.update(overrides)
    return AlexaSettings(**defaults)


def test_run_routine_builds_command_and_returns_success(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: list[str] = []

    def fake_run(command: list[str], **_: object):
        captured.extend(command)
        return subprocess.CompletedProcess(command, 0, stdout="ok\n", stderr="")

    monkeypatch.setattr(runner.subprocess, "run", fake_run)

    result = runner.run_routine(_settings(), "plug_on", None)

    assert result["ok"] is True
    assert result["action"] == "run_routine"
    assert result["routine_name"] == "plug_on"
    assert result["echo_device"] == "Kitchen Echo"
    assert captured == [
        "/tmp/alexa_remote_control.sh",
        "-d",
        "Kitchen Echo",
        "-e",
        "automation:plug_on",
    ]


def test_run_routine_maps_non_zero_exit(monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_run(command: list[str], **_: object):
        return subprocess.CompletedProcess(command, 3, stdout="", stderr="auth failed")

    monkeypatch.setattr(runner.subprocess, "run", fake_run)
    result = runner.run_routine(_settings(), "plug_off", "Living Room Echo")

    assert result["ok"] is False
    assert result["error_type"] == "execution"
    assert result["exit_code"] == 3
    assert result["stderr"] == "auth failed"


def test_run_routine_maps_timeout(monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_run(command: list[str], **_: object):
        raise subprocess.TimeoutExpired(command, 10)

    monkeypatch.setattr(runner.subprocess, "run", fake_run)
    result = runner.run_routine(_settings(), "plug_off", None)

    assert result["ok"] is False
    assert result["error_type"] == "timeout"


def test_run_music_action_requires_query_without_play_routine() -> None:
    with pytest.raises(ConfigError):
        runner.run_music_action(_settings(), "play", query=None)


def test_run_music_action_uses_play_routine_override(monkeypatch: pytest.MonkeyPatch) -> None:
    settings = _settings(music_play_routine="play_focus_music")

    called: dict[str, str] = {}

    def fake_run_routine(_: AlexaSettings, routine_name: str, echo_device: str | None = None):
        called["routine_name"] = routine_name
        called["echo_device"] = echo_device or ""
        return {
            "ok": True,
            "action": "run_routine",
            "command": [],
            "stdout": "ok",
            "stderr": None,
            "exit_code": 0,
            "error_type": None,
            "error_message": None,
            "routine_name": routine_name,
            "music_action": None,
            "echo_device": echo_device,
        }

    monkeypatch.setattr(runner, "run_routine", fake_run_routine)
    result = runner.run_music_action(settings, "play", query=None, echo_device="Office Echo")

    assert result["ok"] is True
    assert called["routine_name"] == "play_focus_music"
    assert called["echo_device"] == "Office Echo"


def test_run_health_check_without_probe_validates_command_path(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(runner, "_resolve_command_path", lambda command: f"/resolved/{command}")
    result = runner.run_health_check(_settings(command="alexa_remote_control.sh"))
    assert result["ok"] is True
    assert result["action"] == "health_check"


def test_run_health_check_with_probe_executes_command(monkeypatch: pytest.MonkeyPatch) -> None:
    settings = _settings(
        command="alexa_remote_control.sh",
        base_args=("--cookie", "/tmp/cookie"),
        health_check_args=("--version",),
    )
    monkeypatch.setattr(runner, "_resolve_command_path", lambda command: f"/resolved/{command}")

    captured: list[str] = []

    def fake_run(command: list[str], **_: object):
        captured.extend(command)
        return subprocess.CompletedProcess(command, 0, stdout="v1", stderr="")

    monkeypatch.setattr(runner.subprocess, "run", fake_run)
    result = runner.run_health_check(settings)

    assert result["ok"] is True
    assert captured == ["alexa_remote_control.sh", "--cookie", "/tmp/cookie", "--version"]
