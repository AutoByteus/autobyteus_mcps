from __future__ import annotations

import anyio
import pytest

pytest.importorskip("mcp")

from mcp.client.session import ClientSession
from mcp.shared.message import SessionMessage

from tts_mcp.config import ServerConfig, load_settings
import tts_mcp.server as server_module


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
async def test_speak_tool_delegates_runner(monkeypatch):
    runner_result = {
        "ok": True,
        "backend": "mlx_audio",
        "platform": "Darwin",
        "machine": "arm64",
        "command": ["mlx_audio.tts.generate", "--text", "hi"],
        "output_path": "/tmp/out.wav",
        "played": True,
        "playback_command": None,
        "warnings": [],
        "stdout": "ok",
        "stderr": None,
        "exit_code": 0,
        "error_type": None,
        "error_message": None,
    }
    expected = {"ok": True}

    monkeypatch.setattr(server_module, "run_speak", lambda **_: runner_result)

    server = server_module.create_server(
        settings=load_settings({"TTS_MCP_AUTO_INSTALL_RUNTIME": "false"}),
        server_config=ServerConfig(name="tts-test"),
    )

    async def run_client(session: ClientSession) -> None:
        result = await session.call_tool("speak", {"text": "hello"})
        assert not result.isError
        assert result.structuredContent == expected

    await _run_with_session(server, run_client)


@pytest.mark.anyio
async def test_speak_tool_returns_reason_on_failure(monkeypatch):
    runner_result = {
        "ok": False,
        "backend": "mlx_audio",
        "platform": "Darwin",
        "machine": "arm64",
        "command": ["mlx_audio.tts.generate", "--text", "hi"],
        "output_path": None,
        "played": False,
        "playback_command": None,
        "warnings": [],
        "stdout": None,
        "stderr": "bad",
        "exit_code": 1,
        "error_type": "execution",
        "error_message": "Backend command failed.",
    }
    expected = {"ok": False, "reason": "Backend command failed."}

    monkeypatch.setattr(server_module, "run_speak", lambda **_: runner_result)

    server = server_module.create_server(
        settings=load_settings({"TTS_MCP_AUTO_INSTALL_RUNTIME": "false"}),
        server_config=ServerConfig(name="tts-test"),
    )

    async def run_client(session: ClientSession) -> None:
        result = await session.call_tool("speak", {"text": "hello"})
        assert not result.isError
        assert result.structuredContent == expected

    await _run_with_session(server, run_client)


@pytest.mark.anyio
async def test_speak_tool_returns_failure_when_playback_not_confirmed(monkeypatch):
    runner_result = {
        "ok": True,
        "backend": "kokoro_onnx",
        "platform": "Linux",
        "machine": "x86_64",
        "command": ["kokoro_onnx.generate", "/tmp/out.wav"],
        "output_path": "/tmp/out.wav",
        "played": False,
        "playback_command": ["ffplay", "-nodisp", "-autoexit", "/tmp/out.wav"],
        "warnings": ["Audio generation succeeded, but playback command failed."],
        "stdout": "ok",
        "stderr": None,
        "exit_code": 0,
        "error_type": None,
        "error_message": None,
    }

    monkeypatch.setattr(server_module, "run_speak", lambda **_: runner_result)

    server = server_module.create_server(
        settings=load_settings({"TTS_MCP_AUTO_INSTALL_RUNTIME": "false"}),
        server_config=ServerConfig(name="tts-test"),
    )

    async def run_client(session: ClientSession) -> None:
        result = await session.call_tool("speak", {"text": "hello", "play": True})
        assert not result.isError
        payload = result.structuredContent
        assert payload["ok"] is False
        assert "playback did not complete" in payload["reason"].lower()

    await _run_with_session(server, run_client)


@pytest.mark.anyio
async def test_speak_tool_allows_generation_only_when_play_false(monkeypatch):
    runner_result = {
        "ok": True,
        "backend": "kokoro_onnx",
        "platform": "Linux",
        "machine": "x86_64",
        "command": ["kokoro_onnx.generate", "/tmp/out.wav"],
        "output_path": "/tmp/out.wav",
        "played": False,
        "playback_command": None,
        "warnings": [],
        "stdout": "ok",
        "stderr": None,
        "exit_code": 0,
        "error_type": None,
        "error_message": None,
    }

    monkeypatch.setattr(server_module, "run_speak", lambda **_: runner_result)

    server = server_module.create_server(
        settings=load_settings({"TTS_MCP_AUTO_INSTALL_RUNTIME": "false"}),
        server_config=ServerConfig(name="tts-test"),
    )

    async def run_client(session: ClientSession) -> None:
        result = await session.call_tool("speak", {"text": "hello", "play": False})
        assert not result.isError
        assert result.structuredContent == {"ok": True}

    await _run_with_session(server, run_client)
