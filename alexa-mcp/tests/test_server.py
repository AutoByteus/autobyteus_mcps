from __future__ import annotations

import anyio
import pytest

pytest.importorskip("mcp")

from mcp.client.session import ClientSession
from mcp.shared.message import SessionMessage

from alexa_mcp.config import AlexaSettings, ServerConfig
import alexa_mcp.server as server_module


def _settings() -> AlexaSettings:
    return AlexaSettings(
        command="alexa_remote_control.sh",
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
async def test_alexa_run_routine_rejects_non_allowlisted(monkeypatch: pytest.MonkeyPatch):
    server = server_module.create_server(
        settings=_settings(),
        server_config=ServerConfig(name="alexa-test"),
    )

    async def run_client(session: ClientSession) -> None:
        result = await session.call_tool(
            "alexa_run_routine",
            {"routine_name": "not_allowlisted"},
        )
        assert not result.isError
        structured = result.structuredContent
        assert structured is not None
        assert structured["ok"] is False
        assert structured["error_type"] == "validation"

    await _run_with_session(server, run_client)


@pytest.mark.anyio
async def test_alexa_health_check_delegates_runner(monkeypatch: pytest.MonkeyPatch):
    expected = {
        "ok": True,
        "action": "health_check",
        "command": ["alexa_remote_control.sh"],
        "stdout": "command available",
        "stderr": None,
        "exit_code": 0,
        "error_type": None,
        "error_message": None,
        "routine_name": None,
        "music_action": None,
        "echo_device": None,
    }
    monkeypatch.setattr(server_module, "run_health_check", lambda _: expected)

    server = server_module.create_server(
        settings=_settings(),
        server_config=ServerConfig(name="alexa-test"),
    )

    async def run_client(session: ClientSession) -> None:
        result = await session.call_tool("alexa_health_check", {})
        assert not result.isError
        assert result.structuredContent == expected

    await _run_with_session(server, run_client)


@pytest.mark.anyio
async def test_alexa_music_control_reports_validation_error(monkeypatch: pytest.MonkeyPatch):
    server = server_module.create_server(
        settings=_settings(),
        server_config=ServerConfig(name="alexa-test"),
    )

    async def run_client(session: ClientSession) -> None:
        result = await session.call_tool(
            "alexa_music_control",
            {"action": "play"},
        )
        assert not result.isError
        structured = result.structuredContent
        assert structured is not None
        assert structured["ok"] is False
        assert structured["error_type"] == "validation"

    await _run_with_session(server, run_client)


@pytest.mark.anyio
async def test_alexa_get_device_status_delegates_runner(monkeypatch: pytest.MonkeyPatch):
    expected = {
        "ok": True,
        "action": "device_status",
        "command": ["alexa_remote_control.sh", "-d", "Office Echo", "-q"],
        "stdout": "{\"currentState\":\"IDLE\"}",
        "stderr": None,
        "exit_code": 0,
        "error_type": None,
        "error_message": None,
        "routine_name": None,
        "music_action": None,
        "echo_device": "Office Echo",
    }

    def fake_run_device_status(*, settings, echo_device: str | None = None):
        assert settings is not None
        assert echo_device == "Office Echo"
        return expected

    monkeypatch.setattr(server_module, "run_device_status", fake_run_device_status)

    server = server_module.create_server(
        settings=_settings(),
        server_config=ServerConfig(name="alexa-test"),
    )

    async def run_client(session: ClientSession) -> None:
        result = await session.call_tool(
            "alexa_get_device_status",
            {"echo_device": "Office Echo"},
        )
        assert not result.isError
        assert result.structuredContent == expected

    await _run_with_session(server, run_client)


@pytest.mark.anyio
async def test_alexa_volume_control_delegates_runner(monkeypatch: pytest.MonkeyPatch):
    expected = {
        "ok": True,
        "action": "volume_control",
        "command": ["alexa_remote_control.sh", "-d", "Office Echo", "-e", "vol:40"],
        "stdout": "ok",
        "stderr": None,
        "exit_code": 0,
        "error_type": None,
        "error_message": None,
        "routine_name": None,
        "music_action": None,
        "echo_device": "Office Echo",
    }

    def fake_run_volume_control(*, settings, direction: str, step: int, echo_device: str | None = None):
        assert settings is not None
        assert direction == "up"
        assert step == 10
        assert echo_device == "Office Echo"
        return expected

    monkeypatch.setattr(server_module, "run_volume_control", fake_run_volume_control)

    server = server_module.create_server(
        settings=_settings(),
        server_config=ServerConfig(name="alexa-test"),
    )

    async def run_client(session: ClientSession) -> None:
        result = await session.call_tool(
            "alexa_volume_control",
            {"direction": "up", "step": 10, "echo_device": "Office Echo"},
        )
        assert not result.isError
        assert result.structuredContent == expected

    await _run_with_session(server, run_client)


@pytest.mark.anyio
async def test_alexa_volume_control_reports_validation_error(monkeypatch: pytest.MonkeyPatch):
    server = server_module.create_server(
        settings=_settings(),
        server_config=ServerConfig(name="alexa-test"),
    )

    async def run_client(session: ClientSession) -> None:
        result = await session.call_tool(
            "alexa_volume_control",
            {"direction": "up", "step": 0},
        )
        assert not result.isError
        structured = result.structuredContent
        assert structured is not None
        assert structured["ok"] is False
        assert structured["error_type"] == "validation"

    await _run_with_session(server, run_client)
