from __future__ import annotations

import subprocess
import time
from pathlib import Path

import pytest

from ssh_mcp.config import SshSettings
from ssh_mcp import runner


def _settings(tmp_path: Path, **overrides: object) -> SshSettings:
    defaults = dict(
        command="ssh",
        base_args=("-o", "BatchMode=yes"),
        timeout_seconds=10,
        allowed_hosts=("host-a",),
        default_host="host-a",
        default_user="ubuntu",
        default_port=22,
        max_command_chars=4000,
        max_output_chars=100,
        health_check_args=("-V",),
        password=None,
        password_file=None,
        session_idle_timeout_seconds=300,
        max_sessions=4,
        session_dir=str(tmp_path / "session-sockets"),
    )
    defaults.update(overrides)
    return SshSettings(**defaults)


def test_run_health_check_returns_config_error_when_command_missing(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setattr(runner.shutil, "which", lambda _command: None)

    result = runner.run_health_check(_settings(tmp_path))

    assert result["ok"] is False
    assert result["error_type"] == "config"


def test_run_open_session_builds_controlmaster_command(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    captured: list[list[str]] = []

    def fake_run(command: list[str], **_: object):
        captured.append(command)
        return subprocess.CompletedProcess(command, 0, stdout="", stderr="")

    monkeypatch.setattr(runner.subprocess, "run", fake_run)

    settings = _settings(tmp_path)
    manager = runner.create_session_manager(settings)
    result = runner.run_open_session(settings, manager, host="host-a", cwd="/srv")

    assert result["ok"] is True
    assert result["session_id"] is not None
    assert len(result["session_id"]) == 8
    assert result["session_count"] == 1
    assert captured[0][:5] == ["ssh", "-o", "BatchMode=yes", "-p", "22"]
    assert "ControlMaster=yes" in captured[0]
    assert "ControlPersist=300" in captured[0]
    assert captured[0][-1] == "echo __ssh_mcp_session_opened__"


def test_run_session_exec_uses_existing_session(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    captured: list[list[str]] = []

    def fake_run(command: list[str], **_: object):
        captured.append(command)
        return subprocess.CompletedProcess(command, 0, stdout="done\n", stderr="")

    monkeypatch.setattr(runner.subprocess, "run", fake_run)

    settings = _settings(tmp_path)
    manager = runner.create_session_manager(settings)
    open_result = runner.run_open_session(settings, manager, host="host-a", cwd="/work")
    session_id = open_result["session_id"]
    assert session_id is not None

    exec_result = runner.run_session_exec(settings, manager, session_id=session_id, command="pwd")

    assert exec_result["ok"] is True
    assert exec_result["stdout"] == "done"
    assert exec_result["session_id"] == session_id
    assert captured[-1][-1] == "cd /work && pwd"


def test_run_close_session_removes_session(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    def fake_run(command: list[str], **_: object):
        return subprocess.CompletedProcess(command, 0, stdout="", stderr="")

    monkeypatch.setattr(runner.subprocess, "run", fake_run)

    settings = _settings(tmp_path)
    manager = runner.create_session_manager(settings)
    open_result = runner.run_open_session(settings, manager, host="host-a")
    session_id = open_result["session_id"]
    assert session_id is not None

    close_result = runner.run_close_session(settings, manager, session_id=session_id)

    assert close_result["ok"] is True
    assert close_result["session_count"] == 0


def test_run_session_exec_rejects_unknown_session(tmp_path: Path) -> None:
    settings = _settings(tmp_path)
    manager = runner.create_session_manager(settings)

    result = runner.run_session_exec(settings, manager, session_id="12345678", command="hostname")

    assert result["ok"] is False
    assert result["error_type"] == "execution"


def test_run_open_session_enforces_max_sessions(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    def fake_run(command: list[str], **_: object):
        return subprocess.CompletedProcess(command, 0, stdout="", stderr="")

    monkeypatch.setattr(runner.subprocess, "run", fake_run)

    settings = _settings(tmp_path, max_sessions=1)
    manager = runner.create_session_manager(settings)

    first = runner.run_open_session(settings, manager, host="host-a")
    second = runner.run_open_session(settings, manager, host="host-a")

    assert first["ok"] is True
    assert second["ok"] is False
    assert second["error_type"] == "validation"
    assert "Session limit reached" in (second["error_message"] or "")


def test_run_open_session_cleans_up_expired_sessions(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    calls: list[list[str]] = []

    def fake_run(command: list[str], **_: object):
        calls.append(command)
        return subprocess.CompletedProcess(command, 0, stdout="", stderr="")

    monkeypatch.setattr(runner.subprocess, "run", fake_run)

    settings = _settings(tmp_path, session_idle_timeout_seconds=1)
    manager = runner.create_session_manager(settings)
    open_result = runner.run_open_session(settings, manager, host="host-a")
    session_id = open_result["session_id"]
    assert session_id is not None

    record = manager.get(session_id)
    assert record is not None
    record.last_used_at = time.time() - 10

    second = runner.run_open_session(settings, manager, host="host-a")

    assert second["ok"] is True
    assert manager.count() == 1
    assert any("-O" in cmd and "exit" in cmd for cmd in calls)


def test_run_open_session_uses_default_host_when_missing(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    captured: list[list[str]] = []

    def fake_run(command: list[str], **_: object):
        captured.append(command)
        return subprocess.CompletedProcess(command, 0, stdout="", stderr="")

    monkeypatch.setattr(runner.subprocess, "run", fake_run)

    settings = _settings(tmp_path, default_host="host-a")
    manager = runner.create_session_manager(settings)
    result = runner.run_open_session(settings, manager, host=None)

    assert result["ok"] is True
    assert result["host"] == "host-a"
    assert "ubuntu@host-a" in captured[0]


def test_run_open_session_enables_password_auth_and_askpass_env(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    captured: list[tuple[list[str], dict[str, str] | None]] = []

    def fake_run(command: list[str], **kwargs: object):
        env = kwargs.get("env")
        captured.append((command, env if isinstance(env, dict) else None))
        return subprocess.CompletedProcess(command, 0, stdout="", stderr="")

    monkeypatch.setattr(runner.subprocess, "run", fake_run)

    settings = _settings(
        tmp_path,
        base_args=(
            "-o",
            "StrictHostKeyChecking=no",
            "-o",
            "UserKnownHostsFile=/dev/null",
        ),
        password="dockerpass",
    )
    manager = runner.create_session_manager(settings)
    result = runner.run_open_session(settings, manager, host="host-a")

    assert result["ok"] is True
    assert captured
    command, env = captured[0]
    assert env is not None
    assert env["SSH_ASKPASS"].endswith("ssh-askpass.sh")
    assert env["SSH_ASKPASS_REQUIRE"] == "force"
    assert env["SSH_MCP_TOOL_PASSWORD"] == "dockerpass"

    destination_index = command.index("ubuntu@host-a")
    assert "BatchMode=no" in command
    assert "PubkeyAuthentication=no" in command
    assert "PreferredAuthentications=password,keyboard-interactive" in command
    assert command.index("BatchMode=no") < destination_index
