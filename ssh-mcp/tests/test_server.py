from __future__ import annotations

import anyio
import pytest

pytest.importorskip("mcp")

from mcp.client.session import ClientSession
from mcp.shared.message import SessionMessage

from ssh_mcp.config import ConfigError, ServerConfig, SshSettings
import ssh_mcp.server as server_module


def _settings() -> SshSettings:
    return SshSettings(
        command="ssh",
        base_args=tuple(),
        timeout_seconds=10,
        allowed_hosts=tuple(),
        default_host=None,
        default_user=None,
        default_port=None,
        max_command_chars=4000,
        max_output_chars=20000,
        health_check_args=("-V",),
        password=None,
        password_file=None,
        session_idle_timeout_seconds=300,
        max_sessions=32,
        session_dir=None,
    )


async def _run_with_session(server, client_callable):
    client_to_server_send, server_read_stream = anyio.create_memory_object_stream[SessionMessage | Exception](0)
    server_to_client_send, client_read_stream = anyio.create_memory_object_stream[SessionMessage](0)

    async def server_task():
        await server._mcp_server.run(  # type: ignore[attr-defined]
            server_read_stream,
            server_to_client_send,
            server._mcp_server.create_initialization_options(),  # type: ignore[attr-defined]
            raise_exceptions=True,
        )

    async with anyio.create_task_group() as tg:
        tg.start_soon(server_task)
        async with ClientSession(client_read_stream, client_to_server_send) as session:
            await session.initialize()
            await client_callable(session)
        await client_to_server_send.aclose()
        await server_to_client_send.aclose()
        tg.cancel_scope.cancel()


@pytest.mark.anyio
async def test_ssh_health_check_delegates_runner(monkeypatch: pytest.MonkeyPatch):
    expected = {
        "ok": True,
        "action": "health_check",
        "command": ["ssh", "-V"],
        "session_id": None,
        "destination": None,
        "host": None,
        "user": None,
        "port": None,
        "remote_command": None,
        "cwd": None,
        "stdout": "OpenSSH_9.0",
        "stderr": None,
        "exit_code": 0,
        "duration_ms": 4,
        "error_type": None,
        "error_message": None,
        "session_count": None,
        "created_at": None,
        "last_used_at": None,
    }
    monkeypatch.setattr(server_module, "run_health_check", lambda _settings: expected)

    server = server_module.create_server(
        settings=_settings(),
        server_config=ServerConfig(name="ssh-test"),
    )

    async def run_client(session: ClientSession) -> None:
        result = await session.call_tool("ssh_health_check", {})
        assert not result.isError
        assert result.structuredContent == expected

    await _run_with_session(server, run_client)


@pytest.mark.anyio
async def test_ssh_open_session_delegates_runner(monkeypatch: pytest.MonkeyPatch):
    expected = {
        "ok": True,
        "action": "open_session",
        "command": ["ssh", "-fN", "host-a"],
        "session_id": "abc12345",
        "destination": "host-a",
        "host": "host-a",
        "user": None,
        "port": None,
        "remote_command": None,
        "cwd": "/srv",
        "stdout": None,
        "stderr": None,
        "exit_code": 0,
        "duration_ms": 20,
        "error_type": None,
        "error_message": None,
        "session_count": 1,
        "created_at": 1.0,
        "last_used_at": 1.0,
    }

    def fake_open(*, settings, manager, host: str, user, port, cwd):
        assert settings is not None
        assert manager is not None
        assert host == "host-a"
        assert user == "ubuntu"
        assert port == 2222
        assert cwd == "/srv"
        return expected

    monkeypatch.setattr(server_module, "run_open_session", fake_open)

    server = server_module.create_server(
        settings=_settings(),
        server_config=ServerConfig(name="ssh-test"),
    )

    async def run_client(session: ClientSession) -> None:
        result = await session.call_tool(
            "ssh_open_session",
            {
                "host": "host-a",
                "user": "ubuntu",
                "port": 2222,
                "cwd": "/srv",
            },
        )
        assert not result.isError
        assert result.structuredContent == expected

    await _run_with_session(server, run_client)


@pytest.mark.anyio
async def test_ssh_open_session_allows_default_host(monkeypatch: pytest.MonkeyPatch):
    expected = {
        "ok": True,
        "action": "open_session",
        "command": ["ssh", "host-a"],
        "session_id": "abc12345",
        "destination": "host-a",
        "host": "host-a",
        "user": None,
        "port": None,
        "remote_command": None,
        "cwd": None,
        "stdout": None,
        "stderr": None,
        "exit_code": 0,
        "duration_ms": 20,
        "error_type": None,
        "error_message": None,
        "session_count": 1,
        "created_at": 1.0,
        "last_used_at": 1.0,
    }

    def fake_open(*, settings, manager, host, user, port, cwd):
        assert settings is not None
        assert manager is not None
        assert host is None
        assert user is None
        assert port is None
        assert cwd is None
        return expected

    monkeypatch.setattr(server_module, "run_open_session", fake_open)

    server = server_module.create_server(
        settings=_settings(),
        server_config=ServerConfig(name="ssh-test"),
    )

    async def run_client(session: ClientSession) -> None:
        result = await session.call_tool("ssh_open_session", {})
        assert not result.isError
        assert result.structuredContent == expected

    await _run_with_session(server, run_client)


@pytest.mark.anyio
async def test_ssh_session_exec_delegates_runner(monkeypatch: pytest.MonkeyPatch):
    expected = {
        "ok": True,
        "action": "session_exec",
        "command": ["ssh", "--", "whoami"],
        "session_id": "abc12345",
        "destination": "host-a",
        "host": "host-a",
        "user": "ubuntu",
        "port": 22,
        "remote_command": "whoami",
        "cwd": None,
        "stdout": "ubuntu",
        "stderr": None,
        "exit_code": 0,
        "duration_ms": 10,
        "error_type": None,
        "error_message": None,
        "session_count": 1,
        "created_at": 1.0,
        "last_used_at": 2.0,
    }

    def fake_exec(*, settings, manager, session_id: str, command: str, cwd):
        assert settings is not None
        assert manager is not None
        assert session_id == "abc12345"
        assert command == "whoami"
        assert cwd is None
        return expected

    monkeypatch.setattr(server_module, "run_session_exec", fake_exec)

    server = server_module.create_server(
        settings=_settings(),
        server_config=ServerConfig(name="ssh-test"),
    )

    async def run_client(session: ClientSession) -> None:
        result = await session.call_tool(
            "ssh_session_exec",
            {
                "session_id": "abc12345",
                "command": "whoami",
            },
        )
        assert not result.isError
        assert result.structuredContent == expected

    await _run_with_session(server, run_client)


@pytest.mark.anyio
async def test_ssh_close_session_delegates_runner(monkeypatch: pytest.MonkeyPatch):
    expected = {
        "ok": True,
        "action": "close_session",
        "command": ["ssh", "-O", "exit", "host-a"],
        "session_id": "abc12345",
        "destination": "host-a",
        "host": "host-a",
        "user": "ubuntu",
        "port": 22,
        "remote_command": None,
        "cwd": None,
        "stdout": None,
        "stderr": None,
        "exit_code": 0,
        "duration_ms": 10,
        "error_type": None,
        "error_message": None,
        "session_count": 0,
        "created_at": 1.0,
        "last_used_at": 2.0,
    }

    def fake_close(*, settings, manager, session_id: str):
        assert settings is not None
        assert manager is not None
        assert session_id == "abc12345"
        return expected

    monkeypatch.setattr(server_module, "run_close_session", fake_close)

    server = server_module.create_server(
        settings=_settings(),
        server_config=ServerConfig(name="ssh-test"),
    )

    async def run_client(session: ClientSession) -> None:
        result = await session.call_tool("ssh_close_session", {"session_id": "abc12345"})
        assert not result.isError
        assert result.structuredContent == expected

    await _run_with_session(server, run_client)


@pytest.mark.anyio
async def test_ssh_session_exec_maps_validation_error(monkeypatch: pytest.MonkeyPatch):
    def fake_exec(**_kwargs):
        raise ConfigError("invalid session id")

    monkeypatch.setattr(server_module, "run_session_exec", fake_exec)

    server = server_module.create_server(
        settings=_settings(),
        server_config=ServerConfig(name="ssh-test"),
    )

    async def run_client(session: ClientSession) -> None:
        result = await session.call_tool(
            "ssh_session_exec",
            {"session_id": "BAD", "command": "whoami"},
        )
        assert not result.isError
        structured = result.structuredContent
        assert structured is not None
        assert structured["ok"] is False
        assert structured["error_type"] == "validation"
        assert "invalid session id" in structured["error_message"]

    await _run_with_session(server, run_client)
