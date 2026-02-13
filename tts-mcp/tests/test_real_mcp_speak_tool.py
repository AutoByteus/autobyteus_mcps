from __future__ import annotations

import os
from pathlib import Path
import platform

import anyio
import pytest

pytest.importorskip("mcp")

from mcp.client.session import ClientSession
from mcp.shared.message import SessionMessage

from tts_mcp.config import ServerConfig, load_settings
import tts_mcp.server as server_module


RUN_REAL_MCP_SPEAK = os.getenv("TTS_MCP_RUN_REAL_MCP_SPEAK") == "1"
IS_APPLE_SILICON_MAC = (
    platform.system() == "Darwin"
    and platform.machine().strip().lower() in {"arm64", "aarch64"}
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


@pytest.mark.skipif(
    not RUN_REAL_MCP_SPEAK,
    reason="Set TTS_MCP_RUN_REAL_MCP_SPEAK=1 to run real MCP speak-tool playback test.",
)
@pytest.mark.skipif(
    not IS_APPLE_SILICON_MAC,
    reason="Real MCP speak-tool playback test requires Apple Silicon macOS.",
)
@pytest.mark.anyio
async def test_real_mcp_speak_tool_plays_audio(tmp_path: Path) -> None:
    settings = load_settings(
        {
            "TTS_MCP_BACKEND": "mlx_audio",
            "TTS_MCP_OUTPUT_DIR": str(tmp_path),
            "TTS_MCP_TIMEOUT_SECONDS": "1200",
            "TTS_MCP_ENFORCE_LATEST": "false",
            "TTS_MCP_MLX_MODEL_PRESET": "kokoro_fast",
            "MLX_TTS_MODEL": "mlx-community/Kokoro-82M-bf16",
        }
    )

    server = server_module.create_server(
        settings=settings,
        server_config=ServerConfig(name="tts-real-mcp-test"),
    )

    async def run_client(session: ClientSession) -> None:
        # Use explicit output_path so artifact persists for verification.
        explicit_output = tmp_path / "real_mcp_speak.wav"
        result = await session.call_tool(
            "speak",
            {
                "text": "Real MCP speak tool playback check.",
                "output_path": str(explicit_output),
            },
        )
        assert not result.isError
        payload = result.structuredContent
        assert payload["ok"] is True
        output_path = explicit_output
        assert output_path.exists()
        assert output_path.stat().st_size > 44

    await _run_with_session(server, run_client)
