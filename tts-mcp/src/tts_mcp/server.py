from __future__ import annotations

import sys
from typing import Literal

from mcp.server.fastmcp import Context, FastMCP

from .config import ServerConfig, TtsSettings, load_settings
from .runtime_bootstrap import bootstrap_runtime
from .runner import run_speak


def create_server(
    settings: TtsSettings | None = None,
    server_config: ServerConfig | None = None,
) -> FastMCP:
    resolved_settings = settings or load_settings()
    resolved_server_config = server_config or ServerConfig.from_env()
    bootstrap_notes = bootstrap_runtime(resolved_settings)
    for note in bootstrap_notes:
        print(f"[tts-mcp] {note}", file=sys.stderr)

    server = FastMCP(
        name=resolved_server_config.name,
        instructions=resolved_server_config.instructions,
    )

    @server.tool(
        name="speak",
        title="Text to speech",
        description=(
            "Speak input text by auto-selecting MLX Audio on Apple Silicon macOS "
            "or llama.cpp TTS on Linux with NVIDIA."
        ),
        structured_output=True,
    )
    async def speak(
        text: str,
        output_path: str | None = None,
        play: bool = True,
        voice: str | None = None,
        speed: float = 1.0,
        language_code: str | None = None,
        backend: Literal["auto", "mlx_audio", "llama_cpp"] | None = None,
        instruct: str | None = None,
        *,
        context: Context | None = None,
    ) -> dict[str, object]:
        if context is not None:
            await context.report_progress(0, 1, "Preparing speech generation")

        result = run_speak(
            settings=resolved_settings,
            text=text,
            output_path=output_path,
            play=play,
            voice=voice,
            speed=speed,
            language_code=language_code,
            preferred_backend=backend,
            instruct=instruct,
        )

        if context is not None:
            await context.report_progress(1, 1, "Speech generation completed")

        if result["ok"]:
            return {"ok": True}
        reason = (result.get("error_message") or "").strip() or "Speech generation failed."
        return {"ok": False, "reason": reason}

    return server


def main() -> None:
    server = create_server()
    server.run()


if __name__ == "__main__":
    main()
