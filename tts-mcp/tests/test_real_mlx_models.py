from __future__ import annotations

import os
from pathlib import Path
import platform

import pytest

from tts_mcp.config import load_settings
from tts_mcp.runner import run_speak


RUN_REAL_MLX_SMOKE = os.getenv("TTS_MCP_RUN_REAL_MLX_SMOKE") == "1"
IS_APPLE_SILICON_MAC = (
    platform.system() == "Darwin"
    and platform.machine().strip().lower() in {"arm64", "aarch64"}
)


@pytest.mark.skipif(
    not RUN_REAL_MLX_SMOKE,
    reason="Set TTS_MCP_RUN_REAL_MLX_SMOKE=1 to run real MLX integration tests.",
)
@pytest.mark.skipif(
    not IS_APPLE_SILICON_MAC,
    reason="Real MLX integration tests require Apple Silicon macOS.",
)
@pytest.mark.parametrize(
    ("preset", "model_id", "instruct"),
    [
        ("kokoro_fast", "mlx-community/Kokoro-82M-bf16", None),
        ("qwen_base_hq", "mlx-community/Qwen3-TTS-12Hz-1.7B-Base-bf16", None),
        (
            "qwen_voicedesign_hq",
            "mlx-community/Qwen3-TTS-12Hz-1.7B-VoiceDesign-bf16",
            "A warm calm studio narrator with clear articulation",
        ),
    ],
)
def test_real_mlx_model_smoke(
    tmp_path: Path,
    preset: str,
    model_id: str,
    instruct: str | None,
) -> None:
    env = {
        "TTS_MCP_BACKEND": "mlx_audio",
        "TTS_MCP_OUTPUT_DIR": str(tmp_path),
        "TTS_MCP_TIMEOUT_SECONDS": "1200",
        "TTS_MCP_MLX_MODEL_PRESET": preset,
        "MLX_TTS_MODEL": model_id,
    }
    if instruct:
        env["MLX_TTS_DEFAULT_INSTRUCT"] = instruct

    settings = load_settings(env)
    output_file = tmp_path / f"{preset}.wav"
    result = run_speak(
        settings=settings,
        text=f"Integration smoke test for {preset}",
        output_path=str(output_file),
        play=False,
    )

    assert result["ok"] is True, result
    assert output_file.exists()
    assert output_file.stat().st_size > 44
