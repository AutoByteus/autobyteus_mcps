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
    expected = {
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

    monkeypatch.setattr(server_module, "run_speak", lambda **_: expected)

    server = server_module.create_server(
        settings=load_settings({"TTS_MCP_AUTO_INSTALL_RUNTIME": "false"}),
        server_config=ServerConfig(name="tts-test"),
    )

    async def run_client(session: ClientSession) -> None:
        result = await session.call_tool("speak", {"text": "hello"})
        assert not result.isError
        assert result.structuredContent == expected

    await _run_with_session(server, run_client)
